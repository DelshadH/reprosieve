from __future__ import annotations

import builtins
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from reprosieve.ddmin import PredicateResult
from reprosieve.predicate import PredicateSpec, run_predicate
from reprosieve.replay import offline_replay, write_replay
from tests.helpers import sample_capsule


def test_offline_replay_substitutes_recorded_model_and_tool_outputs(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    before = set(sys.modules)
    report = offline_replay(sample_capsule())
    assert report.mode == "recorded-output-materialization"
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
    assert "provider_calls" not in decoded
    assert "original_tool_calls" not in decoded
    assert decoded["events_replayed"] == 5


def test_replay_output_is_deterministic(tmp_path: Path) -> None:
    report = offline_replay(sample_capsule())
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_replay(report, first)
    write_replay(report, second)
    assert first.read_bytes() == second.read_bytes()


def test_materialization_leaves_provider_import_canary_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def guarded_import(
        name: str,
        globals: object = None,
        locals: object = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name.partition(".")[0] in {"agents", "openai"}:
            raise AssertionError(f"provider import canary touched: {name}")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    report = offline_replay(sample_capsule())
    assert report.mode == "recorded-output-materialization"


def test_materialization_leaves_original_tool_entrypoint_canary_untouched() -> None:
    capsule = sample_capsule()
    capsule = replace(
        capsule,
        workspace={
            **capsule.workspace,
            "probe.py": "raise AssertionError('original tool entrypoint executed')\n",
        },
    )
    report = offline_replay(capsule)
    assert report.tool_outputs[0]["output"] == {"failure": "needle"}


def test_seed_release_rejects_application_replay_declarations() -> None:
    capsule = sample_capsule()
    application = (
        "import json, os, pathlib\n"
        "from reprosieve_replay_adapter import next_model_output, next_tool_output\n"
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
                "protocol": "reprosieve-recorded-v1",
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

    assert report.result is PredicateResult.INVALID
    assert report.attempts[0].reason == "application_replay_unsupported"
