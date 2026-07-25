from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from pathlib import Path

from runsieve.ddmin import PredicateResult
from runsieve.predicate import PredicateSpec, run_predicate
from runsieve.replay import offline_replay, write_replay
from tests.helpers import sample_capsule


def test_offline_replay_substitutes_recorded_model_and_tool_outputs(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    before = set(sys.modules)
    report = offline_replay(sample_capsule())
    assert report.mode == "offline"
    assert report.provider_calls == 0
    assert report.original_tool_calls == 0
    assert report.model_outputs == (
        {
            "event_id": "response",
            "request_id": "request",
            "output": [{"name": "probe", "type": "function_call"}],
        },
    )
    assert report.tool_outputs == (
        {
            "call_id": "call",
            "event_id": "result",
            "name": "probe",
            "output": {"failure": "needle"},
        },
    )
    assert not (set(sys.modules) - before) & {"openai", "agents"}

    target = tmp_path / "replay.json"
    write_replay(report, target)
    decoded = json.loads(target.read_text(encoding="utf-8"))
    assert decoded["provider_calls"] == 0
    assert decoded["original_tool_calls"] == 0
    assert decoded["events_replayed"] == 5


def test_replay_output_is_deterministic(tmp_path: Path) -> None:
    report = offline_replay(sample_capsule())
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_replay(report, first)
    write_replay(report, second)
    assert first.read_bytes() == second.read_bytes()


def test_declared_application_adapter_executes_with_recorded_interfaces() -> None:
    capsule = sample_capsule()
    application = (
        "import json, os, pathlib\n"
        "from runsieve_replay_adapter import next_model_output, next_tool_output\n"
        "model = next_model_output()\n"
        "tool = next_tool_output('probe')\n"
        "result = {'model_type': model[0]['type'], 'failure': tool['failure']}\n"
        "pathlib.Path(os.environ['RUNSIEVE_APPLICATION_RESULT']).write_text("
        "json.dumps(result), encoding='utf-8')\n"
    )
    predicate = (
        "import json, os, pathlib\n"
        "result = json.loads(pathlib.Path("
        "os.environ['RUNSIEVE_APPLICATION_RESULT']).read_text(encoding='utf-8'))\n"
        "raise SystemExit(0 if result == "
        "{'model_type': 'function_call', 'failure': 'needle'} else 1)\n"
    )
    capsule = replace(
        capsule,
        metadata={
            **capsule.metadata,
            "application_replay": {
                "protocol": "runsieve-recorded-v1",
                "argv": ["python", "replay_application.py"],
            },
        },
        workspace={
            **capsule.workspace,
            "replay_application.py": application,
            "verify_application.py": predicate,
        },
    )

    report = run_predicate(
        capsule,
        PredicateSpec(("python", "verify_application.py"), timeout_seconds=3),
    )

    assert report.result is PredicateResult.REPRODUCES
    assert report.attempts[0].application_replay is True
    assert report.attempts[0].application_exit_code == 0
    assert "OPENAI_API_KEY" not in os.environ or report.attempts[0].provider_calls == 0
