from __future__ import annotations

import json
from pathlib import Path

from runsieve.capsule import canonical_json

ROOT = Path(__file__).resolve().parents[1]


def test_maturity_status_preserves_external_and_manual_blockers() -> None:
    path = ROOT / "docs" / "maturity-status.json"
    raw = path.read_bytes()
    status = json.loads(raw)

    assert canonical_json(status) == raw
    assert status["schema_version"] == 1
    assert status["recommendation"] == "ready-for-0.1.0-alpha-review"
    assert set(status["levels"]) == {"0.1", "0.5", "1.0"}
    assert status["levels"]["0.1"]["status"] == "ready-for-alpha-review"
    assert status["levels"]["0.5"]["status"] == "not-ready"
    assert status["levels"]["1.0"]["status"] == "not-ready"

    half_blockers = {
        item["id"] for item in status["levels"]["0.5"]["remaining"]
    }
    assert {
        "permissioned-real-case",
        "several-real-reductions",
        "independent-human-review",
    }.issubset(half_blockers)

    one_blockers = {
        item["id"] for item in status["levels"]["1.0"]["remaining"]
    }
    assert {
        "multiple-active-maintainers",
        "sustained-external-use",
        "stable-release-history",
        "canonical-history-owner-actions",
    }.issubset(one_blockers)


def test_maturity_status_does_not_invent_real_cases() -> None:
    status = json.loads(
        (ROOT / "docs" / "maturity-status.json").read_text(encoding="utf-8")
    )
    registry = json.loads(
        (ROOT / "docs" / "case-studies" / "registry.json").read_text(
            encoding="utf-8"
        )
    )

    assert registry["cases"] == []
    assert all(
        item["kind"] != "permissioned-real-case"
        for item in status["levels"]["0.5"]["evidence"]
    )
