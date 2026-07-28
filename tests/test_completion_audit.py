from __future__ import annotations

import json
from pathlib import Path

from reprosieve.capsule import canonical_json

ROOT = Path(__file__).resolve().parents[1]
_EXPECTED = {
    "contract-v2-lineage": "verified-technical",
    "independent-0.1-candidate": "verified-technical",
    "canonical-migration-preparation": "verified-technical",
    "canonical-migration-execution": "verified-technical",
    "reproducible-release-engineering": "verified-technical",
    "0.1-publication": "publication-authorized-registry-ready",
    "framework-application-replay": "verified-technical",
    "0.5-readiness": "blocked-external",
    "permissioned-case-infrastructure": "verified-technical",
    "permissioned-real-cases": "blocked-external",
    "stable-formats-security-governance": "verified-technical",
    "1.0-readiness": "blocked-external",
}
_EXPECTED_PRINCIPLES = {
    "producer-verifier-separation",
    "hashes-are-byte-integrity-only",
    "assertions-independently-measured",
    "no-op-mutations-invalid",
    "unsupported-evidence-fails",
    "invalid-predicate-not-absent",
    "synthetic-not-real-impact",
    "reexecution-claims-exact",
    "security-boundary-named",
    "audit-hooks-defense-in-depth",
    "capsule-entrypoints-never-silent",
    "format-compatibility-durable",
    "release-gates-use-concrete-artifacts",
    "platform-claims-use-platform-evidence",
    "evidence-clean-tree",
    "evidence-commit-ancestral",
    "source-changes-invalidate-evidence",
    "no-gate-or-security-weakening",
    "no-fabricated-external-facts",
    "marketing-does-not-exceed-evidence",
}


def test_completion_audit_is_canonical_and_preserves_full_scope() -> None:
    path = ROOT / "docs" / "completion-audit.json"
    raw = path.read_bytes()
    audit = json.loads(raw)

    assert canonical_json(audit) == raw
    assert set(audit) == {
        "audited_at",
        "recommendation",
        "requirements",
        "schema_version",
    }
    assert audit["schema_version"] == 1
    assert audit["recommendation"] == "ready-for-0.1.0a2-publication"
    requirements = {item["id"]: item for item in audit["requirements"]}
    assert {
        requirement_id: item["status"]
        for requirement_id, item in requirements.items()
    } == _EXPECTED
    for item in requirements.values():
        assert item["evidence"]
        for evidence in item["evidence"]:
            if "source" in evidence:
                assert (ROOT / evidence["source"]).exists(), evidence["source"]
        if item["status"].startswith("blocked"):
            assert item["blockers"]
        else:
            assert item["blockers"] == []


def test_completion_audit_does_not_convert_infrastructure_into_maturity() -> None:
    audit = json.loads(
        (ROOT / "docs" / "completion-audit.json").read_text(encoding="utf-8")
    )
    maturity = json.loads(
        (ROOT / "docs" / "maturity-status.json").read_text(encoding="utf-8")
    )
    registry = json.loads(
        (ROOT / "docs" / "case-studies" / "registry.json").read_text(
            encoding="utf-8"
        )
    )
    progress = json.loads((ROOT / "PROGRESS.json").read_text(encoding="utf-8"))
    requirements = {item["id"]: item for item in audit["requirements"]}

    assert registry["cases"] == []
    assert requirements["permissioned-real-cases"]["status"] == "blocked-external"
    assert requirements["0.5-readiness"]["status"] != "verified-technical"
    assert requirements["1.0-readiness"]["status"] != "verified-technical"
    assert maturity["levels"]["0.5"]["status"] == "not-ready"
    assert maturity["levels"]["1.0"]["status"] == "not-ready"
    assert {item["status"] for item in progress["tasks"].values()} == {"passed"}
    assert {item["status"] for item in progress["gates"].values()} == {"passed"}


def test_non_negotiable_principles_have_current_tree_evidence() -> None:
    path = ROOT / "docs" / "principles-audit.json"
    raw = path.read_bytes()
    audit = json.loads(raw)

    assert canonical_json(audit) == raw
    assert audit["schema_version"] == 1
    principles = {item["id"]: item for item in audit["principles"]}
    assert set(principles) == _EXPECTED_PRINCIPLES
    assert {item["status"] for item in principles.values()} == {
        "verified-current-tree"
    }
    assert all(item["evidence"] for item in principles.values())
    for item in principles.values():
        for reference in item["evidence"]:
            assert (ROOT / reference).exists(), reference
