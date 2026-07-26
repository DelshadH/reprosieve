from __future__ import annotations

import json
import math
import platform
import sys
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from typing import Any

from agents import (
    Agent,
    FunctionTool,
    Model,
    ModelProvider,
    ModelResponse,
    RunConfig,
    Runner,
    Usage,
)
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage

from ..capsule import canonical_json
from ..redact import RedactionPolicy, RedactionReport, redact_with_report
from ..schema import Capsule, Event, JsonValue, validate_capsule
from .openai_agents import ensure_supported_agents_version

Application = Callable[[Any], Awaitable[Any]]

_PROTOCOL = "openai-agents-public-v1"
_MATCHING = "ordered-exact-v1"


class ApplicationReplayUnsupported(ValueError):
    """The capsule or SDK behavior is outside the declared adapter boundary."""


class ApplicationReplayDivergence(ValueError):
    """The rerun departed from the recorded ordered interaction trajectory."""


@dataclass(slots=True)
class _ReportCounter:
    replacements: int = 0
    scanned_nodes: int = 0
    reasons: dict[str, int] | None = None

    def add(self, report: RedactionReport) -> None:
        self.replacements += report.replacements
        self.scanned_nodes += report.scanned_nodes
        if self.reasons is None:
            self.reasons = {}
        for reason, count in report.reasons.items():
            self.reasons[reason] = self.reasons.get(reason, 0) + count

    def to_json(self) -> dict[str, JsonValue]:
        return {
            "replacements": self.replacements,
            "reasons": dict(sorted((self.reasons or {}).items())),
            "scanned_nodes": self.scanned_nodes,
        }


@dataclass(frozen=True, slots=True)
class ApplicationCaptureResult:
    capsule: Capsule
    redaction_report: dict[str, JsonValue]
    provider_calls: int
    original_tool_calls: int
    application_executions: int
    application_replay_eligible: bool
    final_output: JsonValue


@dataclass(frozen=True, slots=True)
class ApplicationReplayReport:
    mode: str
    adapter: str
    matching: str
    application_executions: int
    model_calls_consumed: int
    tool_calls_consumed: int
    provider_resolution_attempts: int
    original_tool_calls: int
    all_interactions_consumed: bool
    final_output: JsonValue

    def to_json(self) -> dict[str, JsonValue]:
        return {
            "adapter": self.adapter,
            "all_interactions_consumed": self.all_interactions_consumed,
            "application_executions": self.application_executions,
            "final_output": self.final_output,
            "matching": self.matching,
            "mode": self.mode,
            "model_calls_consumed": self.model_calls_consumed,
            "original_tool_calls": self.original_tool_calls,
            "provider_resolution_attempts": self.provider_resolution_attempts,
            "tool_calls_consumed": self.tool_calls_consumed,
        }


def _json_value(value: Any, *, label: str) -> JsonValue:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ApplicationReplayUnsupported(f"{label} contains a non-finite number")
        return value
    if isinstance(value, Enum):
        return _json_value(value.value, label=label)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _json_value(
            model_dump(mode="json", exclude_none=True),
            label=label,
        )
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value), label=label)
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise ApplicationReplayUnsupported(f"{label} has a non-string object key")
            result[key] = _json_value(child, label=label)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_value(child, label=label) for child in value]
    raise ApplicationReplayUnsupported(f"{label} is not bounded JSON")


def _parse_arguments(arguments: str, *, label: str) -> JsonValue:
    try:
        parsed = json.loads(arguments)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ApplicationReplayDivergence(f"{label} are not valid JSON") from exc
    return _json_value(parsed, label=label)


def _same_json(left: JsonValue, right: JsonValue) -> bool:
    return canonical_json(left) == canonical_json(right)


def _tool_definition(tool: FunctionTool) -> dict[str, JsonValue]:
    return {
        "description": tool.description,
        "name": tool.name,
        "params_json_schema": _json_value(
            tool.params_json_schema,
            label=f"tool {tool.name} schema",
        ),
        "strict_json_schema": tool.strict_json_schema,
    }


def _model_settings_payload(model_settings: Any) -> dict[str, JsonValue]:
    if not is_dataclass(model_settings) or isinstance(model_settings, type):
        raise ApplicationReplayUnsupported("model settings are not a supported SDK dataclass")
    raw = asdict(model_settings)
    supported = {
        "frequency_penalty",
        "max_tokens",
        "parallel_tool_calls",
        "presence_penalty",
        "temperature",
        "tool_choice",
        "top_p",
        "truncation",
    }
    unsupported = sorted(
        key for key, value in raw.items() if value is not None and key not in supported
    )
    if unsupported:
        raise ApplicationReplayUnsupported(
            f"model settings use unsupported fields: {', '.join(unsupported)}"
        )
    result: dict[str, JsonValue] = {}
    for key in sorted(supported):
        value = raw.get(key)
        if value is None:
            continue
        safe_key = "max_output_count" if key == "max_tokens" else key
        result[safe_key] = _json_value(value, label=f"model setting {key}")
    return result


def _usage_payload(usage: Usage) -> dict[str, JsonValue]:
    input_details = _json_value(usage.input_tokens_details, label="input usage details")
    output_details = _json_value(usage.output_tokens_details, label="output usage details")
    if (
        not isinstance(input_details, dict)
        or any(value != 0 for value in input_details.values())
        or not isinstance(output_details, dict)
        or any(value != 0 for value in output_details.values())
        or usage.request_usage_entries
    ):
        raise ApplicationReplayUnsupported("detailed model usage is not supported")
    return {
        "input_count": usage.input_tokens,
        "output_count": usage.output_tokens,
        "requests": usage.requests,
        "total_count": usage.total_tokens,
    }


def _usage_from_payload(value: Any) -> Usage:
    if not isinstance(value, dict) or set(value) != {
        "input_count",
        "output_count",
        "requests",
        "total_count",
    }:
        raise ApplicationReplayUnsupported("recorded model usage is unsupported")
    if any(not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in value.values()):
        raise ApplicationReplayUnsupported("recorded model usage is malformed")
    return Usage(
        requests=value["requests"],
        input_tokens=value["input_count"],
        output_tokens=value["output_count"],
        total_tokens=value["total_count"],
    )


def _validate_tool(tool: FunctionTool) -> None:
    if (
        tool.is_enabled is not True
        or tool.tool_input_guardrails
        or tool.tool_output_guardrails
        or tool.needs_approval is not False
        or tool.timeout_seconds is not None
        or tool.defer_loading
        or tool.custom_data_extractor is not None
    ):
        raise ApplicationReplayUnsupported(
            f"tool {tool.name} uses unsupported dynamic, approval, guardrail, timeout, or loading behavior"
        )


def _validate_tools(tools: tuple[FunctionTool, ...]) -> None:
    names: set[str] = set()
    for tool in tools:
        if not isinstance(tool, FunctionTool):
            raise ApplicationReplayUnsupported("only public FunctionTool adapters are supported")
        _validate_tool(tool)
        if tool.name in names:
            raise ApplicationReplayUnsupported("tool names must be unique")
        names.add(tool.name)


def _request_payload(
    *,
    system_instructions: str | None,
    input: Any,
    model_settings: Any,
    tools: list[Any],
    output_schema: Any,
    handoffs: list[Any],
    previous_response_id: str | None,
    conversation_id: str | None,
    prompt: Any,
) -> dict[str, JsonValue]:
    if output_schema is not None:
        raise ApplicationReplayUnsupported("structured output schemas are not supported")
    if handoffs:
        raise ApplicationReplayUnsupported("handoffs are not supported")
    if previous_response_id is not None or conversation_id is not None or prompt is not None:
        raise ApplicationReplayUnsupported(
            "response chaining, conversations, and prompt templates are not supported"
        )
    if any(not isinstance(tool, FunctionTool) for tool in tools):
        raise ApplicationReplayUnsupported("only FunctionTool model inputs are supported")
    return {
        "conversation_id": None,
        "input": _json_value(input, label="model input"),
        "model_settings": _model_settings_payload(model_settings),
        "previous_response_id": None,
        "prompt": None,
        "system_instructions": system_instructions,
        "tools": [_tool_definition(tool) for tool in tools],
    }


def _response_payload(response: ModelResponse) -> dict[str, JsonValue]:
    return {
        "output": _json_value(response.output, label="model output"),
        "request_id": response.request_id,
        "response_id": response.response_id,
        "usage": _usage_payload(response.usage),
    }


def _result_output(value: Any) -> JsonValue:
    final = getattr(value, "final_output", value)
    return _json_value(final, label="application result")


def _validate_agent(
    agent: Agent[Any],
    *,
    model: Model,
    tools: tuple[FunctionTool, ...],
) -> None:
    if agent.model is not model:
        raise ApplicationReplayDivergence("application did not use the injected model")
    if len(agent.tools) != len(tools) or any(
        actual is not expected for actual, expected in zip(agent.tools, tools, strict=True)
    ):
        raise ApplicationReplayDivergence("application did not use only the injected tool wrappers")
    if agent.handoffs or agent.mcp_servers:
        raise ApplicationReplayUnsupported("handoffs and MCP servers are not supported")


class _CaptureModel(Model):
    def __init__(self, session: OpenAIAgentsCaptureSession, delegate: Model) -> None:
        self._session = session
        self._delegate = delegate

    async def get_response(
        self,
        system_instructions: str | None,
        input: Any,
        model_settings: Any,
        tools: list[Any],
        output_schema: Any,
        handoffs: list[Any],
        tracing: Any,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: Any,
    ) -> ModelResponse:
        payload = _request_payload(
            system_instructions=system_instructions,
            input=input,
            model_settings=model_settings,
            tools=tools,
            output_schema=output_schema,
            handoffs=handoffs,
            previous_response_id=previous_response_id,
            conversation_id=conversation_id,
            prompt=prompt,
        )
        request_id = self._session._record_model_request(payload)
        self._session.provider_calls += 1
        response = await self._delegate.get_response(
            system_instructions,
            input,
            model_settings,
            tools,
            output_schema,
            handoffs,
            tracing,
            previous_response_id=previous_response_id,
            conversation_id=conversation_id,
            prompt=prompt,
        )
        self._session._record_model_response(
            request_id=request_id,
            payload=_response_payload(response),
        )
        return response

    async def stream_response(
        self,
        *_args: Any,
        **_kwargs: Any,
    ) -> AsyncIterator[Any]:
        raise ApplicationReplayUnsupported("streaming application capture is not supported")
        yield  # pragma: no cover


class OpenAIAgentsCaptureSession:
    """Capture one explicit SDK application run through public Model and FunctionTool wrappers."""

    def __init__(
        self,
        *,
        live_model: Model,
        original_tools: tuple[FunctionTool, ...],
        redaction_policy: RedactionPolicy,
        trace_id: str,
    ) -> None:
        _validate_tools(original_tools)
        self._policy = redaction_policy
        self._trace_id = trace_id
        self._counter = _ReportCounter()
        self._events: list[Event] = [
            Event(
                id="e000000",
                kind="run",
                parent_id=None,
                sequence=0,
                payload={"workflow_name": "openai-agents-application"},
            )
        ]
        self._last_model_response: str | None = None
        self._last_tool_result: str | None = None
        self._application_executions = 0
        self._runner_calls = 0
        self.provider_calls = 0
        self.original_tool_calls = 0
        self._closed = False
        self.model: Model = _CaptureModel(self, live_model)
        self.tools = tuple(
            self._capture_tool(tool)
            for tool in original_tools
        )

    def _redact(self, payload: object) -> JsonValue:
        redacted, report = redact_with_report(payload, policy=self._policy)
        self._counter.add(report)
        return redacted

    def _add_event(
        self,
        *,
        kind: str,
        payload: object,
        dependencies: tuple[str, ...] = (),
    ) -> str:
        event_id = f"e{len(self._events):06d}"
        self._events.append(
            Event(
                id=event_id,
                kind=kind,  # type: ignore[arg-type]
                parent_id="e000000",
                sequence=len(self._events),
                payload=self._redact(payload),
                dependencies=dependencies,
            )
        )
        return event_id

    def _record_model_request(self, payload: dict[str, JsonValue]) -> str:
        dependencies = (
            (self._last_tool_result,)
            if self._last_tool_result is not None
            else ()
        )
        return self._add_event(
            kind="model_request",
            payload=payload,
            dependencies=dependencies,
        )

    def _record_model_response(
        self,
        *,
        request_id: str,
        payload: dict[str, JsonValue],
    ) -> None:
        self._last_model_response = self._add_event(
            kind="model_response",
            payload=payload,
            dependencies=(request_id,),
        )

    def _capture_tool(self, tool: FunctionTool) -> FunctionTool:
        async def invoke(context: Any, arguments: str) -> Any:
            parsed = _parse_arguments(arguments, label=f"tool {tool.name} arguments")
            dependencies = (
                (self._last_model_response,)
                if self._last_model_response is not None
                else ()
            )
            call_id = self._add_event(
                kind="tool_call",
                payload={"arguments": parsed, "name": tool.name},
                dependencies=dependencies,
            )
            self.original_tool_calls += 1
            output = await tool.on_invoke_tool(context, arguments)
            self._last_tool_result = self._add_event(
                kind="tool_result",
                payload={
                    "name": tool.name,
                    "output": _json_value(output, label=f"tool {tool.name} output"),
                },
                dependencies=(call_id,),
            )
            return output

        return FunctionTool(
            name=tool.name,
            description=tool.description,
            params_json_schema=tool.params_json_schema,
            on_invoke_tool=invoke,
            strict_json_schema=tool.strict_json_schema,
        )

    async def run(
        self,
        starting_agent: Agent[Any],
        input: Any,
        *,
        context: Any = None,
        max_turns: int = 10,
    ) -> Any:
        if self._closed:
            raise ApplicationReplayUnsupported("capture session is already closed")
        if self._runner_calls:
            raise ApplicationReplayUnsupported("exactly one Runner invocation is supported")
        _validate_agent(starting_agent, model=self.model, tools=self.tools)
        self._runner_calls += 1
        return await Runner.run(
            starting_agent,
            input,
            context=context,
            max_turns=max_turns,
            run_config=RunConfig(
                tracing_disabled=True,
                trace_include_sensitive_data=False,
            ),
        )

    async def execute(self, application: Application) -> ApplicationCaptureResult:
        if self._application_executions:
            raise ApplicationReplayUnsupported("application entry point already executed")
        self._application_executions = 1
        result = await application(self)
        self._closed = True
        if self._runner_calls != 1 or self.provider_calls < 1:
            raise ApplicationReplayUnsupported(
                "application entry point must execute exactly one model-backed Runner run"
            )
        final_output = self._redact(_result_output(result))
        eligible = self._counter.replacements == 0
        sdk_version = ensure_supported_agents_version()
        metadata: dict[str, JsonValue] = {
            "adapter": {
                "name": "openai-agents",
                "public_interface": "Model/FunctionTool",
                "version": sdk_version,
            },
            "application_replay": {
                "eligible": eligible,
                "matching": _MATCHING,
                "protocol": _PROTOCOL,
                "redaction_replacements": self._counter.replacements,
            },
            "runtime": {
                "implementation": platform.python_implementation(),
                "platform": sys.platform,
                "python": platform.python_version(),
            },
        }
        capsule = Capsule(
            schema_version="1",
            trace_id=self._trace_id,
            events=tuple(self._events),
            metadata=metadata,
        )
        validate_capsule(capsule)
        return ApplicationCaptureResult(
            capsule=capsule,
            redaction_report=self._counter.to_json(),
            provider_calls=self.provider_calls,
            original_tool_calls=self.original_tool_calls,
            application_executions=self._application_executions,
            application_replay_eligible=eligible,
            final_output=final_output,
        )


class _DenyProvider(ModelProvider):
    def __init__(self) -> None:
        self.attempts = 0

    def get_model(self, model_name: str | None) -> Model:
        del model_name
        self.attempts += 1
        raise ApplicationReplayDivergence("live model provider resolution was attempted")


class _ReplayModel(Model):
    def __init__(self, session: OpenAIAgentsReplaySession) -> None:
        self._session = session

    async def get_response(
        self,
        system_instructions: str | None,
        input: Any,
        model_settings: Any,
        tools: list[Any],
        output_schema: Any,
        handoffs: list[Any],
        tracing: Any,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: Any,
    ) -> ModelResponse:
        del tracing
        self._session._raise_deferred()
        actual = _request_payload(
            system_instructions=system_instructions,
            input=input,
            model_settings=model_settings,
            tools=tools,
            output_schema=output_schema,
            handoffs=handoffs,
            previous_response_id=previous_response_id,
            conversation_id=conversation_id,
            prompt=prompt,
        )
        _request, response = self._session._consume_pair(
            call_kind="model_request",
            result_kind="model_response",
            actual=actual,
            mismatch="model request",
        )
        self._session.model_calls_consumed += 1
        return self._session._model_response(response)

    async def stream_response(
        self,
        *_args: Any,
        **_kwargs: Any,
    ) -> AsyncIterator[Any]:
        raise ApplicationReplayUnsupported("streaming application replay is not supported")
        yield  # pragma: no cover


class OpenAIAgentsReplaySession:
    """Rerun one SDK application entry point using recorded interactions only."""

    def __init__(
        self,
        capsule: Capsule,
        *,
        original_tools: tuple[FunctionTool, ...],
    ) -> None:
        validate_capsule(capsule)
        _validate_tools(original_tools)
        adapter = capsule.metadata.get("adapter")
        replay = capsule.metadata.get("application_replay")
        if (
            not isinstance(adapter, dict)
            or adapter.get("name") != "openai-agents"
            or adapter.get("public_interface") != "Model/FunctionTool"
            or adapter.get("version") != ensure_supported_agents_version()
            or not isinstance(replay, dict)
            or replay.get("protocol") != _PROTOCOL
            or replay.get("matching") != _MATCHING
        ):
            raise ApplicationReplayUnsupported("capsule lacks a supported application-replay declaration")
        if replay.get("eligible") is not True:
            raise ApplicationReplayUnsupported(
                "capsule has redacted matching fields and is not application-replay eligible"
            )
        if len(capsule.events) < 3 or capsule.events[0].kind != "run":
            raise ApplicationReplayUnsupported("application replay needs a run and interaction pairs")
        interactions = capsule.events[1:]
        if any(
            event.kind
            not in {"model_request", "model_response", "tool_call", "tool_result"}
            for event in interactions
        ):
            raise ApplicationReplayUnsupported("capsule contains unsupported application events")
        self._events = interactions
        self._cursor = 0
        self._application_executions = 0
        self._runner_calls = 0
        self._closed = False
        self._deferred: ApplicationReplayDivergence | None = None
        self.model_calls_consumed = 0
        self.tool_calls_consumed = 0
        self.original_tool_calls = 0
        self._provider = _DenyProvider()
        self._original_tools = original_tools
        self._original_handlers = tuple(tool.on_invoke_tool for tool in original_tools)
        self.model: Model = _ReplayModel(self)
        self.tools = tuple(
            self._replay_tool(tool)
            for tool in original_tools
        )

    def _install_original_tool_canaries(self) -> None:
        for tool in self._original_tools:
            async def deny(_context: Any, _arguments: str, *, name: str = tool.name) -> Any:
                self.original_tool_calls += 1
                raise ApplicationReplayDivergence(
                    f"original tool execution attempted for {name}"
                )

            tool.on_invoke_tool = deny

    def _restore_original_tools(self) -> None:
        for tool, handler in zip(
            self._original_tools,
            self._original_handlers,
            strict=True,
        ):
            tool.on_invoke_tool = handler

    def _raise_deferred(self) -> None:
        if self._deferred is not None:
            raise self._deferred

    def _consume_pair(
        self,
        *,
        call_kind: str,
        result_kind: str,
        actual: dict[str, JsonValue],
        mismatch: str,
    ) -> tuple[Event, Event]:
        if self._cursor + 1 >= len(self._events):
            raise ApplicationReplayDivergence(f"unexpected extra {mismatch}")
        call = self._events[self._cursor]
        result = self._events[self._cursor + 1]
        if call.kind != call_kind or result.kind != result_kind:
            raise ApplicationReplayDivergence(
                f"expected {call_kind}/{result_kind} at interaction {self._cursor}"
            )
        if not isinstance(call.payload, dict) or not _same_json(call.payload, actual):
            raise ApplicationReplayDivergence(f"{mismatch} differs from the recorded interaction")
        self._cursor += 2
        return call, result

    def _model_response(self, event: Event) -> ModelResponse:
        payload = event.payload
        if not isinstance(payload, dict):
            raise ApplicationReplayUnsupported("recorded model response is malformed")
        raw_output = payload.get("output")
        raw_usage = payload.get("usage")
        if not isinstance(raw_output, list) or not isinstance(raw_usage, dict):
            raise ApplicationReplayUnsupported("recorded model response is incomplete")
        output: list[Any] = []
        function_calls: list[ResponseFunctionToolCall] = []
        for item in raw_output:
            if not isinstance(item, dict):
                raise ApplicationReplayUnsupported("recorded model output item is malformed")
            if item.get("type") == "function_call":
                parsed = ResponseFunctionToolCall.model_validate(item)
                output.append(parsed)
                function_calls.append(parsed)
            elif item.get("type") == "message":
                output.append(ResponseOutputMessage.model_validate(item))
            else:
                raise ApplicationReplayUnsupported(
                    f"recorded model output type {item.get('type')!r} is unsupported"
                )
        if len(function_calls) > 1:
            raise ApplicationReplayUnsupported("parallel tool calls are not supported")
        if function_calls:
            if self._cursor >= len(self._events):
                raise ApplicationReplayDivergence("recorded function call has no tool interaction")
            expected = self._events[self._cursor]
            if expected.kind != "tool_call" or not isinstance(expected.payload, dict):
                raise ApplicationReplayDivergence("recorded function call is not followed by a tool call")
            function_call = function_calls[0]
            expected_arguments = expected.payload.get("arguments")
            actual_arguments = _parse_arguments(
                function_call.arguments,
                label=f"tool {function_call.name} arguments",
            )
            if (
                expected.payload.get("name") != function_call.name
                or not _same_json(expected_arguments, actual_arguments)
            ):
                raise ApplicationReplayDivergence(
                    "recorded model output and tool arguments diverge"
                )
        usage = _usage_from_payload(raw_usage)
        response_id = payload.get("response_id")
        request_id = payload.get("request_id")
        if response_id is not None and not isinstance(response_id, str):
            raise ApplicationReplayUnsupported("recorded response ID is malformed")
        if request_id is not None and not isinstance(request_id, str):
            raise ApplicationReplayUnsupported("recorded request ID is malformed")
        return ModelResponse(
            output=output,
            usage=usage,
            response_id=response_id,
            request_id=request_id,
        )

    def _replay_tool(self, tool: FunctionTool) -> FunctionTool:
        async def invoke(_context: Any, arguments: str) -> Any:
            actual_arguments = _parse_arguments(
                arguments,
                label=f"tool {tool.name} arguments",
            )
            if self._cursor + 1 >= len(self._events):
                self._deferred = ApplicationReplayDivergence(
                    f"unexpected original tool request {tool.name}"
                )
                return None
            call = self._events[self._cursor]
            result = self._events[self._cursor + 1]
            if (
                call.kind != "tool_call"
                or result.kind != "tool_result"
                or not isinstance(call.payload, dict)
                or call.payload.get("name") != tool.name
                or not _same_json(call.payload.get("arguments"), actual_arguments)
            ):
                self._deferred = ApplicationReplayDivergence(
                    f"tool arguments for {tool.name} differ from the recorded interaction"
                )
                return None
            if not isinstance(result.payload, dict) or result.payload.get("name") != tool.name:
                self._deferred = ApplicationReplayDivergence(
                    f"tool result for {tool.name} is malformed"
                )
                return None
            if "error" in result.payload:
                self._deferred = ApplicationReplayDivergence(
                    f"recorded tool error for {tool.name} is unsupported"
                )
                return None
            self._cursor += 2
            self.tool_calls_consumed += 1
            return result.payload.get("output")

        return FunctionTool(
            name=tool.name,
            description=tool.description,
            params_json_schema=tool.params_json_schema,
            on_invoke_tool=invoke,
            strict_json_schema=tool.strict_json_schema,
        )

    async def run(
        self,
        starting_agent: Agent[Any],
        input: Any,
        *,
        context: Any = None,
        max_turns: int = 10,
    ) -> Any:
        if self._closed:
            raise ApplicationReplayUnsupported("replay session is already closed")
        if self._runner_calls:
            raise ApplicationReplayUnsupported("exactly one Runner invocation is supported")
        _validate_agent(starting_agent, model=self.model, tools=self.tools)
        self._runner_calls += 1
        result = await Runner.run(
            starting_agent,
            input,
            context=context,
            max_turns=max_turns,
            run_config=RunConfig(
                model_provider=self._provider,
                tracing_disabled=True,
                trace_include_sensitive_data=False,
            ),
        )
        self._raise_deferred()
        return result

    async def execute(self, application: Application) -> ApplicationReplayReport:
        if self._application_executions:
            raise ApplicationReplayUnsupported("application entry point already executed")
        self._application_executions = 1
        self._install_original_tool_canaries()
        try:
            result = await application(self)
            self._raise_deferred()
            if self.original_tool_calls:
                raise ApplicationReplayDivergence(
                    "original tool execution was attempted during application replay"
                )
            if self._provider.attempts:
                raise ApplicationReplayDivergence(
                    "live model provider resolution was attempted during application replay"
                )
            if self._runner_calls != 1:
                raise ApplicationReplayUnsupported(
                    "application entry point must execute exactly one Runner run"
                )
            if self._cursor != len(self._events):
                raise ApplicationReplayDivergence("application left recorded interactions unconsumed")
            return ApplicationReplayReport(
                mode="application-replay",
                adapter="openai-agents",
                matching=_MATCHING,
                application_executions=self._application_executions,
                model_calls_consumed=self.model_calls_consumed,
                tool_calls_consumed=self.tool_calls_consumed,
                provider_resolution_attempts=self._provider.attempts,
                original_tool_calls=self.original_tool_calls,
                all_interactions_consumed=True,
                final_output=_result_output(result),
            )
        finally:
            self._closed = True
            self._restore_original_tools()
