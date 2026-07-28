from __future__ import annotations

import json
from pathlib import Path

from reprosieve.capsule import canonical_json

ROOT = Path(__file__).resolve().parents[1]


def test_maturity_status_records_alpha_candidate_and_external_blockers() -> None:
    path = ROOT / "docs" / "maturity-status.json"
    raw = path.read_bytes()
    status = json.loads(raw)

    assert canonical_json(status) == raw
    assert status["schema_version"] == 1
    assert status["recommendation"] == "ready-for-0.1.0a2-publication"
    assert set(status["levels"]) == {"0.1", "0.5", "1.0"}
    assert (
        status["levels"]["0.1"]["status"]
        == "publication-authorized"
    )
    assert status["levels"]["0.5"]["status"] == "not-ready"
    assert status["levels"]["1.0"]["status"] == "not-ready"

    alpha_remaining = {
        item["id"] for item in status["levels"]["0.1"]["remaining"]
    }
    assert alpha_remaining == set()

    half_blockers = {
        item["id"] for item in status["levels"]["0.5"]["remaining"]
    }
    assert {
        "permissioned-real-case",
        "several-real-reductions",
    }.issubset(half_blockers)
    assert "independent-human-review" not in half_blockers

    one_blockers = {
        item["id"] for item in status["levels"]["1.0"]["remaining"]
    }
    assert {
        "multiple-active-maintainers",
        "sustained-external-use",
        "stable-release-history",
    }.issubset(one_blockers)
    assert "canonical-history-owner-actions" not in one_blockers


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
