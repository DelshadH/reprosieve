from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from agents import Agent, FunctionTool, Model, ModelResponse, Usage
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)

from runsieve.adapters.openai_agents_replay import (
    ApplicationReplayDivergence,
    ApplicationReplayUnsupported,
    OpenAIAgentsCaptureSession,
    OpenAIAgentsReplaySession,
)
from runsieve.capsule import canonical_json, write_capsule
from runsieve.ddmin import PredicateResult
from runsieve.hierarchy import minimize_capsule
from runsieve.redact import RedactionPolicy
from runsieve.safeio import ensure_new_path
from runsieve.verify import verify_one_minimal

ROOT = Path(__file__).resolve().parents[1]
_SHA = re.compile(r"^[0-9a-f]{40}$")


class _ScriptedModel(Model):
    def __init__(self) -> None:
        self.calls = 0
        self.outputs: list[list[Any]] = [
            [
                ResponseFunctionToolCall(
                    arguments='{"value":7}',
                    call_id="call-evidence-1",
                    name="probe",
                    type="function_call",
                )
            ],
            [
                ResponseOutputMessage(
                    id="message-evidence-1",
                    content=[
                        ResponseOutputText(
                            annotations=[],
                            text="needle confirmed",
                            type="output_text",
                        )
                    ],
                    role="assistant",
                    status="completed",
                    type="message",
                )
            ],
        ]

    async def get_response(self, *args: Any, **kwargs: Any) -> ModelResponse:
        del args, kwargs
        self.calls += 1
        if not self.outputs:
            raise RuntimeError("synthetic evidence model received an extra call")
        return ModelResponse(
            output=self.outputs.pop(0),
            usage=Usage(requests=1, input_tokens=3, output_tokens=2, total_tokens=5),
            response_id=f"evidence-response-{self.calls}",
        )

    async def stream_response(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise RuntimeError("streaming is outside the evidence fixture")
        yield  # pragma: no cover


def _tool(counter: dict[str, int]) -> FunctionTool:
    async def invoke(_context: Any, arguments: str) -> dict[str, object]:
        counter["calls"] += 1
        parsed = json.loads(arguments)
        return {"failure": "needle", "value": parsed["value"]}

    return FunctionTool(
        name="probe",
        description="Return a synthetic failure marker.",
        params_json_schema={
            "additionalProperties": False,
            "properties": {"value": {"type": "integer"}},
            "required": ["value"],
            "type": "object",
        },
        on_invoke_tool=invoke,
    )


async def _application(session: Any) -> Any:
    agent = Agent(
        name="RunSieve evidence application",
        instructions="Call probe once, then report the marker.",
        model=session.model,
        tools=list(session.tools),
    )
    return await session.run(agent, "find failure")


def _run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(path: Path, *, root: Path, role: str) -> dict[str, object]:
    return {
        "bytes": path.stat().st_size,
        "path": path.relative_to(root).as_posix(),
        "role": role,
        "sha256": _sha256(path),
    }


def _write_json(path: Path, value: object) -> None:
    with path.open("xb") as stream:
        stream.write(canonical_json(value))


def generate_evidence(output: Path, *, commit: str) -> dict[str, str]:
    if _SHA.fullmatch(commit) is None:
        raise ValueError("application replay evidence requires a full commit SHA")
    target = ensure_new_path(output, label="application replay evidence output")
    target.mkdir()
    original_counter = {"calls": 0}
    live_model = _ScriptedModel()
    tool = _tool(original_counter)
    captured = _run(
        OpenAIAgentsCaptureSession(
            live_model=live_model,
            original_tools=(tool,),
            redaction_policy=RedactionPolicy(salt=b"runsieve-application-evidence-v1"),
            trace_id="trace_application_evidence",
        ).execute(_application)
    )
    source = replace(
        captured.capsule,
        workspace={"irrelevant.txt": "remove this declared unit"},
    )
    live_model.calls = 0
    original_counter["calls"] = 0

    def evaluate(candidate: Any) -> PredicateResult:
        try:
            report = _run(
                OpenAIAgentsReplaySession(
                    candidate,
                    original_tools=(tool,),
                ).execute(_application)
            )
        except ApplicationReplayDivergence:
            return PredicateResult.ABSENT
        except (ApplicationReplayUnsupported, ValueError):
            return PredicateResult.INVALID
        return (
            PredicateResult.REPRODUCES
            if report.final_output == "needle confirmed"
            else PredicateResult.ABSENT
        )

    minimized = minimize_capsule(
        source,
        evaluate,
        predicate_identity="openai-agents-application-replay-evidence-v1",
    )
    minimality = verify_one_minimal(minimized.capsule, evaluate)
    replay = _run(
        OpenAIAgentsReplaySession(
            minimized.capsule,
            original_tools=(tool,),
        ).execute(_application)
    )
    if (
        not minimality.is_one_minimal
        or replay.final_output != "needle confirmed"
        or live_model.calls
        or original_counter["calls"]
    ):
        raise RuntimeError("application replay producer did not satisfy its fixture")

    source_path = target / "source.runsieve"
    reduced_path = target / "reduced.runsieve"
    write_capsule(
        source,
        source_path,
        redaction_report=captured.redaction_report,
    )
    write_capsule(
        minimized.capsule,
        reduced_path,
        redaction_report=captured.redaction_report,
    )
    report_path = target / "producer-report.json"
    _write_json(
        report_path,
        {
            "application_capture": {
                "application_executions": captured.application_executions,
                "original_tool_calls": captured.original_tool_calls,
                "provider_calls": captured.provider_calls,
                "replay_eligible": captured.application_replay_eligible,
            },
            "application_replay": replay.to_json(),
            "commit": commit,
            "minimality": minimality.to_json(),
            "reduction": minimized.report.to_json(),
            "schema_version": 1,
        },
    )
    producer_path = Path(__file__).resolve()
    manifest_path = target / "evidence.json"
    _write_json(
        manifest_path,
        {
            "artifacts": [
                _artifact(source_path, root=target, role="source-capsule"),
                _artifact(reduced_path, root=target, role="reduced-capsule"),
                _artifact(report_path, root=target, role="producer-report"),
            ],
            "commit": commit,
            "gate": "RS-05-AR1",
            "producer": {
                "bytes": producer_path.stat().st_size,
                "path": producer_path.relative_to(ROOT).as_posix(),
                "sha256": _sha256(producer_path),
            },
            "schema_version": 1,
        },
    )
    return {
        "path": manifest_path.name,
        "sha256": _sha256(manifest_path),
    }


def _clean_commit() -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if status.returncode or status.stdout:
        raise ValueError("application replay evidence requires a clean Git tree")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    commit = head.stdout.strip()
    if head.returncode or _SHA.fullmatch(commit) is None:
        raise ValueError("application replay evidence cannot resolve HEAD")
    return commit


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        print(
            "usage: python -m scripts.generate_application_replay_evidence OUTPUT",
            file=sys.stderr,
        )
        return 2
    try:
        reference = generate_evidence(Path(arguments[0]), commit=_clean_commit())
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"application replay evidence generation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(reference, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
