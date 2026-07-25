from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .capsule import canonical_json
from .schema import Capsule, JsonValue, safe_relative_path, validate_capsule

_APPLICATION_PROTOCOL = "runsieve-recorded-v1"


@dataclass(frozen=True, slots=True)
class OfflineReplay:
    mode: str
    trace_id: str
    events_replayed: int
    model_outputs: tuple[dict[str, JsonValue], ...]
    tool_outputs: tuple[dict[str, JsonValue], ...]
    provider_calls: int = 0
    original_tool_calls: int = 0

    def to_json(self) -> dict[str, JsonValue]:
        return {
            "events_replayed": self.events_replayed,
            "mode": self.mode,
            "model_outputs": list(self.model_outputs),
            "original_tool_calls": self.original_tool_calls,
            "provider_calls": self.provider_calls,
            "tool_outputs": list(self.tool_outputs),
            "trace_id": self.trace_id,
        }


@dataclass(frozen=True, slots=True)
class ApplicationReplaySpec:
    argv: tuple[str, ...]
    protocol: str = _APPLICATION_PROTOCOL


def application_replay_spec(capsule: Capsule) -> ApplicationReplaySpec | None:
    raw = capsule.metadata.get("application_replay")
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != {"argv", "protocol"}:
        raise ValueError("application replay declaration fields are invalid")
    argv = raw.get("argv")
    if (
        raw.get("protocol") != _APPLICATION_PROTOCOL
        or not isinstance(argv, list)
        or len(argv) < 2
        or any(not isinstance(part, str) or not part or "\x00" in part for part in argv)
    ):
        raise ValueError("application replay declaration is invalid")
    argv_text = tuple(str(part) for part in argv)
    if Path(argv_text[0]).name.casefold() not in {
        "python",
        "python3",
        "python.exe",
        "py",
    }:
        raise ValueError("application replay declaration is invalid")
    entrypoint = safe_relative_path(argv_text[1], label="application replay entrypoint")
    if entrypoint not in capsule.workspace:
        raise ValueError("application replay entrypoint is not embedded")
    return ApplicationReplaySpec(argv=(argv_text[0], entrypoint, *argv_text[2:]))


def replay_adapter_source() -> str:
    return (
        "import json, os, pathlib\n"
        "_data=json.loads(pathlib.Path(os.environ['RUNSIEVE_REPLAY']).read_text("
        "encoding='utf-8'))\n"
        "_models=list(_data['model_outputs'])\n"
        "_tools=list(_data['tool_outputs'])\n"
        "_model_index=0\n"
        "_tool_index=0\n"
        "def next_model_output():\n"
        " global _model_index\n"
        " if _model_index >= len(_models): raise RuntimeError('recorded model outputs exhausted')\n"
        " item=_models[_model_index]\n"
        " _model_index+=1\n"
        " return item.get('output')\n"
        "def next_tool_output(expected_name=None):\n"
        " global _tool_index\n"
        " if _tool_index >= len(_tools): raise RuntimeError('recorded tool outputs exhausted')\n"
        " item=_tools[_tool_index]\n"
        " if expected_name is not None and item.get('name') != expected_name:\n"
        "  raise RuntimeError('recorded tool trajectory mismatch')\n"
        " _tool_index+=1\n"
        " if 'error' in item: raise RuntimeError('recorded tool error')\n"
        " return item.get('output')\n"
        "def consumption():\n"
        " return {'model_outputs':_model_index,'tool_outputs':_tool_index}\n"
    )


def offline_replay(capsule: Capsule) -> OfflineReplay:
    """Materialize deterministic recorded outputs without executing application code.

    This module intentionally has no SDK, provider, HTTP, socket, or tool-execution imports.
    """
    validate_capsule(capsule)
    kinds = {event.id: event.kind for event in capsule.events}
    model_outputs: list[dict[str, JsonValue]] = []
    tool_outputs: list[dict[str, JsonValue]] = []
    for event in capsule.events:
        if event.kind == "model_response":
            request_ids = [
                dependency
                for dependency in event.dependencies
                if kinds[dependency] == "model_request"
            ]
            model_outputs.append(
                {
                    "event_id": event.id,
                    "request_id": request_ids[0],
                    "output": (
                        event.payload.get("output")
                        if isinstance(event.payload, dict)
                        else event.payload
                    ),
                }
            )
        elif event.kind == "tool_result":
            call_ids = [
                dependency for dependency in event.dependencies if kinds[dependency] == "tool_call"
            ]
            item: dict[str, JsonValue] = {
                "call_id": call_ids[0],
                "event_id": event.id,
            }
            if isinstance(event.payload, dict):
                if "name" in event.payload:
                    item["name"] = event.payload["name"]
                if "output" in event.payload:
                    item["output"] = event.payload["output"]
                if "error" in event.payload:
                    item["error"] = event.payload["error"]
            else:
                item["output"] = event.payload
            tool_outputs.append(item)
    return OfflineReplay(
        mode="offline",
        trace_id=capsule.trace_id,
        events_replayed=len(capsule.events),
        model_outputs=tuple(model_outputs),
        tool_outputs=tuple(tool_outputs),
    )


def write_replay(report: OfflineReplay, path: str | Path) -> None:
    target = Path(path)
    if target.exists() or target.is_symlink():
        raise FileExistsError("replay output already exists")
    with target.open("xb") as stream:
        stream.write(canonical_json(report.to_json()))
