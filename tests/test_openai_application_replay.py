from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

agents = pytest.importorskip("agents", reason="openai extra is required for application replay")
from agents import Agent, FunctionTool, Model, ModelResponse
from agents.usage import Usage
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
from runsieve.capsule import capsule_bytes
from runsieve.ddmin import PredicateResult
from runsieve.hierarchy import minimize_capsule
from runsieve.redact import RedactionPolicy
from runsieve.verify import verify_one_minimal


def _run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


class ScriptedModel(Model):
    def __init__(self, outputs: list[list[Any]]) -> None:
        self.outputs = list(outputs)
        self.calls = 0

    async def get_response(self, *args: Any, **kwargs: Any) -> ModelResponse:
        del args, kwargs
        self.calls += 1
        if not self.outputs:
            raise AssertionError("live model received an unexpected call")
        return ModelResponse(
            output=self.outputs.pop(0),
            usage=Usage(requests=1, input_tokens=3, output_tokens=2, total_tokens=5),
            response_id=f"response-{self.calls}",
        )

    async def stream_response(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise AssertionError("streaming was not requested")
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


def _scripted_tool_run() -> list[list[Any]]:
    return [
        [
            ResponseFunctionToolCall(
                arguments='{"value":7}',
                call_id="call-1",
                name="probe",
                type="function_call",
            )
        ],
        [
            ResponseOutputMessage(
                id="message-1",
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


def test_public_sdk_application_capture_and_replay_execute_application_without_live_calls(
    tmp_path: Path,
) -> None:
    original_tool = {"calls": 0}
    live_model = ScriptedModel(_scripted_tool_run())
    tool = _tool(original_tool)
    application = {"calls": 0}

    async def run_application(session: Any) -> Any:
        application["calls"] += 1
        agent = Agent(
            name="Replay fixture",
            instructions="Call probe once, then report the marker.",
            model=session.model,
            tools=list(session.tools),
        )
        return await session.run(agent, "find failure")

    capture = OpenAIAgentsCaptureSession(
        live_model=live_model,
        original_tools=(tool,),
        redaction_policy=RedactionPolicy(salt=b"capture-fixture-salt"),
        trace_id="trace_application_fixture",
    )
    captured = _run(capture.execute(run_application))

    assert application["calls"] == 1
    assert live_model.calls == 2
    assert original_tool["calls"] == 1
    assert captured.provider_calls == 2
    assert captured.original_tool_calls == 1
    assert captured.application_replay_eligible is True, captured.redaction_report
    assert [event.kind for event in captured.capsule.events] == [
        "run",
        "model_request",
        "model_response",
        "tool_call",
        "tool_result",
        "model_request",
        "model_response",
    ]
    (tmp_path / "capture.runsieve").write_bytes(
        capsule_bytes(
            captured.capsule,
            redaction_report=captured.redaction_report,
        )
    )

    application["calls"] = 0
    live_model.calls = 0
    original_tool["calls"] = 0
    replay = OpenAIAgentsReplaySession(
        captured.capsule,
        original_tools=(tool,),
    )
    report = _run(replay.execute(run_application))

    assert application["calls"] == 1
    assert report.application_executions == 1
    assert report.model_calls_consumed == 2
    assert report.tool_calls_consumed == 1
    assert report.provider_resolution_attempts == 0
    assert report.original_tool_calls == 0
    assert report.final_output == "needle confirmed"
    assert report.all_interactions_consumed is True
    assert live_model.calls == 0
    assert original_tool["calls"] == 0


def test_tool_argument_divergence_fails_before_original_tool_execution() -> None:
    original_tool = {"calls": 0}
    live_model = ScriptedModel(_scripted_tool_run())
    tool = _tool(original_tool)

    async def run_application(session: Any) -> Any:
        agent = Agent(
            name="Replay fixture",
            instructions="Call probe once, then report the marker.",
            model=session.model,
            tools=list(session.tools),
        )
        return await session.run(agent, "find failure")

    captured = _run(
        OpenAIAgentsCaptureSession(
            live_model=live_model,
            original_tools=(tool,),
            redaction_policy=RedactionPolicy(salt=b"capture-fixture-salt"),
            trace_id="trace_divergence_fixture",
        ).execute(run_application)
    )
    events = list(captured.capsule.events)
    call_index = next(index for index, event in enumerate(events) if event.kind == "tool_call")
    call = events[call_index]
    assert isinstance(call.payload, dict)
    events[call_index] = replace(
        call,
        payload={**call.payload, "arguments": {"value": 8}},
    )
    divergent = replace(captured.capsule, events=tuple(events))

    live_model.calls = 0
    original_tool["calls"] = 0
    with pytest.raises(ApplicationReplayDivergence, match="tool arguments"):
        _run(
            OpenAIAgentsReplaySession(
                divergent,
                original_tools=(tool,),
            ).execute(run_application)
        )
    assert live_model.calls == 0
    assert original_tool["calls"] == 0


def test_redacted_matching_fields_make_application_replay_ineligible() -> None:
    canary = "Bearer APPLICATION-REPLAY-CANARY"
    live_model = ScriptedModel(
        [
            [
                ResponseOutputMessage(
                    id="message-redacted",
                    content=[
                        ResponseOutputText(
                            annotations=[],
                            text="safe result",
                            type="output_text",
                        )
                    ],
                    role="assistant",
                    status="completed",
                    type="message",
                )
            ]
        ]
    )

    async def run_application(session: Any) -> Any:
        agent = Agent(
            name="Redaction fixture",
            instructions="Return a safe result.",
            model=session.model,
        )
        result = await session.run(agent, canary)
        return {"authorization": canary, "result": result.final_output}

    captured = _run(
        OpenAIAgentsCaptureSession(
            live_model=live_model,
            original_tools=(),
            redaction_policy=RedactionPolicy(
                salt=b"capture-redaction-salt",
                exact_canaries=(canary,),
            ),
            trace_id="trace_redacted_application",
        ).execute(run_application)
    )

    data = capsule_bytes(
        captured.capsule,
        redaction_report=captured.redaction_report,
    )
    assert canary.encode() not in data
    assert canary not in json.dumps(captured.final_output)
    assert captured.application_replay_eligible is False
    with pytest.raises(ApplicationReplayUnsupported, match="redacted matching fields"):
        OpenAIAgentsReplaySession(captured.capsule, original_tools=())


def test_changed_application_instructions_diverge_without_live_calls() -> None:
    original_tool = {"calls": 0}
    live_model = ScriptedModel(_scripted_tool_run())
    tool = _tool(original_tool)

    async def capture_application(session: Any) -> Any:
        agent = Agent(
            name="Replay fixture",
            instructions="Call probe once, then report the marker.",
            model=session.model,
            tools=list(session.tools),
        )
        return await session.run(agent, "find failure")

    captured = _run(
        OpenAIAgentsCaptureSession(
            live_model=live_model,
            original_tools=(tool,),
            redaction_policy=RedactionPolicy(salt=b"instruction-divergence-salt"),
            trace_id="trace_instruction_divergence",
        ).execute(capture_application)
    )

    async def changed_application(session: Any) -> Any:
        agent = Agent(
            name="Replay fixture",
            instructions="Do not call any tool.",
            model=session.model,
            tools=list(session.tools),
        )
        return await session.run(agent, "find failure")

    live_model.calls = 0
    original_tool["calls"] = 0
    with pytest.raises(ApplicationReplayDivergence, match="model request"):
        _run(
            OpenAIAgentsReplaySession(
                captured.capsule,
                original_tools=(tool,),
            ).execute(changed_application)
        )
    assert live_model.calls == 0
    assert original_tool["calls"] == 0


def test_original_tool_injection_is_rejected_before_runner_execution() -> None:
    original_tool = {"calls": 0}
    live_model = ScriptedModel(_scripted_tool_run())
    tool = _tool(original_tool)

    async def capture_application(session: Any) -> Any:
        agent = Agent(
            name="Replay fixture",
            instructions="Call probe once, then report the marker.",
            model=session.model,
            tools=list(session.tools),
        )
        return await session.run(agent, "find failure")

    captured = _run(
        OpenAIAgentsCaptureSession(
            live_model=live_model,
            original_tools=(tool,),
            redaction_policy=RedactionPolicy(salt=b"tool-injection-salt"),
            trace_id="trace_tool_injection",
        ).execute(capture_application)
    )

    async def unsafe_application(session: Any) -> Any:
        agent = Agent(
            name="Replay fixture",
            instructions="Call probe once, then report the marker.",
            model=session.model,
            tools=[tool],
        )
        return await session.run(agent, "find failure")

    live_model.calls = 0
    original_tool["calls"] = 0
    with pytest.raises(ApplicationReplayDivergence, match="injected tool wrappers"):
        _run(
            OpenAIAgentsReplaySession(
                captured.capsule,
                original_tools=(tool,),
            ).execute(unsafe_application)
        )
    assert live_model.calls == 0
    assert original_tool["calls"] == 0


def test_early_application_exit_rejects_unconsumed_recorded_interactions() -> None:
    original_tool = {"calls": 0}
    live_model = ScriptedModel(_scripted_tool_run())
    tool = _tool(original_tool)

    async def capture_application(session: Any) -> Any:
        agent = Agent(
            name="Replay fixture",
            instructions="Call probe once, then report the marker.",
            model=session.model,
            tools=list(session.tools),
        )
        return await session.run(agent, "find failure")

    captured = _run(
        OpenAIAgentsCaptureSession(
            live_model=live_model,
            original_tools=(tool,),
            redaction_policy=RedactionPolicy(salt=b"unconsumed-interaction-salt"),
            trace_id="trace_unconsumed_interactions",
        ).execute(capture_application)
    )

    async def early_exit_application(session: Any) -> Any:
        agent = Agent(
            name="Replay fixture",
            instructions="Call probe once, then report the marker.",
            model=session.model,
            tools=list(session.tools),
            tool_use_behavior="stop_on_first_tool",
        )
        return await session.run(agent, "find failure")

    live_model.calls = 0
    original_tool["calls"] = 0
    with pytest.raises(ApplicationReplayDivergence, match="unconsumed"):
        _run(
            OpenAIAgentsReplaySession(
                captured.capsule,
                original_tools=(tool,),
            ).execute(early_exit_application)
        )
    assert live_model.calls == 0
    assert original_tool["calls"] == 0


def test_reducer_produces_independently_verified_application_replay_capsule() -> None:
    original_tool = {"calls": 0}
    live_model = ScriptedModel(_scripted_tool_run())
    tool = _tool(original_tool)

    async def run_application(session: Any) -> Any:
        agent = Agent(
            name="Replay fixture",
            instructions="Call probe once, then report the marker.",
            model=session.model,
            tools=list(session.tools),
        )
        return await session.run(agent, "find failure")

    captured = _run(
        OpenAIAgentsCaptureSession(
            live_model=live_model,
            original_tools=(tool,),
            redaction_policy=RedactionPolicy(salt=b"application-reduction-salt"),
            trace_id="trace_application_reduction",
        ).execute(run_application)
    )
    source = replace(
        captured.capsule,
        workspace={"irrelevant.txt": "remove me"},
    )
    live_model.calls = 0
    original_tool["calls"] = 0

    def evaluate(candidate: Any) -> PredicateResult:
        try:
            report = _run(
                OpenAIAgentsReplaySession(
                    candidate,
                    original_tools=(tool,),
                ).execute(run_application)
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

    reduced = minimize_capsule(
        source,
        evaluate,
        predicate_identity="openai-agents-application-replay-v1",
    )
    proof = verify_one_minimal(reduced.capsule, evaluate)
    final_report = _run(
        OpenAIAgentsReplaySession(
            reduced.capsule,
            original_tools=(tool,),
        ).execute(run_application)
    )

    assert reduced.capsule.workspace == {}
    assert proof.is_one_minimal is True
    assert final_report.all_interactions_consumed is True
    assert final_report.final_output == "needle confirmed"
    assert live_model.calls == 0
    assert original_tool["calls"] == 0


def test_direct_original_tool_call_hits_measured_canary_and_is_restored() -> None:
    original_tool = {"calls": 0}
    live_model = ScriptedModel(_scripted_tool_run())
    tool = _tool(original_tool)

    async def capture_application(session: Any) -> Any:
        agent = Agent(
            name="Replay fixture",
            instructions="Call probe once, then report the marker.",
            model=session.model,
            tools=list(session.tools),
        )
        return await session.run(agent, "find failure")

    captured = _run(
        OpenAIAgentsCaptureSession(
            live_model=live_model,
            original_tools=(tool,),
            redaction_policy=RedactionPolicy(salt=b"direct-tool-canary-salt"),
            trace_id="trace_direct_tool_canary",
        ).execute(capture_application)
    )
    live_model.calls = 0
    original_tool["calls"] = 0
    replay = OpenAIAgentsReplaySession(
        captured.capsule,
        original_tools=(tool,),
    )

    async def unsafe_application(session: Any) -> Any:
        try:
            await tool.on_invoke_tool(None, '{"value":7}')
        except ApplicationReplayDivergence:
            pass
        agent = Agent(
            name="Replay fixture",
            instructions="Call probe once, then report the marker.",
            model=session.model,
            tools=list(session.tools),
        )
        return await session.run(agent, "find failure")

    with pytest.raises(ApplicationReplayDivergence, match="original tool execution"):
        _run(replay.execute(unsafe_application))
    assert replay.original_tool_calls == 1
    assert original_tool["calls"] == 0

    _run(tool.on_invoke_tool(None, '{"value":7}'))
    assert original_tool["calls"] == 1
