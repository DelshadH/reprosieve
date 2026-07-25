from __future__ import annotations

import json
import sys
from pathlib import Path

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
