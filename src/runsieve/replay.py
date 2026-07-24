from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .capsule import canonical_json
from .schema import Capsule, JsonValue, validate_capsule


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


def offline_replay(capsule: Capsule) -> OfflineReplay:
    """Build a deterministic replay only from recorded values.

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
