from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

import pytest

agents = pytest.importorskip("agents", reason="openai extra is required for adapter proof")
from agents import (
    function_span,
    generation_span,
    guardrail_span,
    handoff_span,
    set_trace_processors,
    trace,
)
from agents.tracing import TracingProcessor

from runsieve.adapters.openai_agents import (
    RunSieveTraceProcessor,
    ensure_supported_agents_version,
    install_processor,
)
from runsieve.capsule import load_capsule
from runsieve.schema import validate_capsule


class CanaryProcessor(TracingProcessor):
    def __init__(self) -> None:
        self.calls = 0

    def on_trace_start(self, trace: Any) -> None:
        self.calls += 1

    def on_trace_end(self, trace: Any) -> None:
        self.calls += 1

    def on_span_start(self, span: Any) -> None:
        self.calls += 1

    def on_span_end(self, span: Any) -> None:
        self.calls += 1

    def shutdown(self) -> None:
        return None

    def force_flush(self) -> None:
        return None


def test_public_processor_captures_real_sdk_spans_without_duplicate_export(
    tmp_path: Path,
) -> None:
    canary = "OPENAI-ADAPTER-SECRET-CANARY"
    canary_exporter = CanaryProcessor()
    set_trace_processors([canary_exporter])
    output = tmp_path / "capture.runsieve"
    processor = RunSieveTraceProcessor(
        output_path=output,
        exact_canaries=(canary,),
        environment_names=(),
    )
    install_processor(processor, retain_existing=False)
    assert isinstance(processor, TracingProcessor)

    with trace("RunSieve adapter fixture", metadata={"authorization": f"Bearer {canary}"}):
        with generation_span(
            input=[{"role": "user", "content": canary}],
            output=[{"type": "function_call", "name": "probe", "arguments": "{}"}],
            model="fixture-model",
            model_config={"temperature": 0},
        ):
            pass
        with function_span(
            "probe",
            input=json.dumps({"api_key": canary}),
            output=json.dumps({"failure": "needle"}),
        ):
            pass
        with handoff_span("triage", "resolver"):
            pass
        with guardrail_span("synthetic", triggered=True):
            pass

    assert canary_exporter.calls == 0
    assert output.is_file()
    assert canary.encode() not in output.read_bytes()
    capsule = load_capsule(output)
    validate_capsule(capsule)
    kinds = [event.kind for event in capsule.events]
    assert kinds.count("model_request") == 1
    assert kinds.count("model_response") == 1
    assert kinds.count("tool_call") == 1
    assert kinds.count("tool_result") == 1
    assert "handoff" in kinds
    assert "guardrail" in kinds
    assert processor.failure_reason is None
    assert processor.completed_capsules == (capsule,)
    set_trace_processors([])


def test_retaining_an_existing_exporter_requires_explicit_opt_in() -> None:
    canary = CanaryProcessor()
    set_trace_processors([canary])
    processor = RunSieveTraceProcessor()
    install_processor(processor, retain_existing=True)
    with trace("explicit duplicate fixture"):
        pass
    assert canary.calls == 2
    assert len(processor.completed_capsules) == 1
    set_trace_processors([])


def test_declared_workspace_and_environment_are_bounded_redacted_and_sanitized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canary = "FILENAME-SECRET-CANARY"
    workspace_name = f"fixture-{canary}.txt"
    (tmp_path / workspace_name).write_text(f"value={canary}", encoding="utf-8")
    monkeypatch.setenv("RUNSIEVE_FIXTURE_VALUE", canary)
    output = tmp_path / "bounded.runsieve"
    processor = RunSieveTraceProcessor(
        output_path=output,
        exact_canaries=(canary,),
        workspace_root=tmp_path,
        workspace_paths=(workspace_name,),
        environment_names=("RUNSIEVE_FIXTURE_VALUE",),
    )
    install_processor(processor)
    with trace("workspace fixture"):
        pass
    data = output.read_bytes()
    assert canary.encode() not in data
    capsule = load_capsule(output)
    assert len(capsule.workspace) == 1
    safe_name = next(iter(capsule.workspace))
    assert canary not in safe_name
    assert canary not in capsule.workspace[safe_name]
    assert canary not in capsule.environment["RUNSIEVE_FIXTURE_VALUE"]
    set_trace_processors([])


def test_malformed_or_oversized_span_fails_closed_without_echoing_payload() -> None:
    canary = "MALFORMED-SPAN-CANARY"

    class FakeTrace:
        trace_id = "trace_fake"
        workflow_name = "fake"
        group_id = None
        metadata: ClassVar[dict[str, object]] = {}

    class FakeSpan:
        trace_id = "trace_fake"
        span_id = "span_fake"
        parent_id = None

        def export(self) -> dict[str, object]:
            return {"span_data": {"type": "custom", "data": canary * 1000}}

    processor = RunSieveTraceProcessor(
        exact_canaries=(canary,),
        max_string_bytes=128,
    )
    processor.on_trace_start(FakeTrace())
    processor.on_span_start(FakeSpan())
    processor.on_span_end(FakeSpan())
    processor.on_trace_end(FakeTrace())
    assert processor.completed_capsules == ()
    assert processor.failure_reason == "capture payload exceeded a configured limit"
    assert canary not in repr(processor)


def test_supported_sdk_range_matches_installed_release() -> None:
    assert ensure_supported_agents_version() == "0.18.3"
