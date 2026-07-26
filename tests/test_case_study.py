from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from reprosieve.capsule import canonical_json
from scripts.verify_case_study import verify_case_study_package

ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _case_study(tmp_path: Path) -> Path:
    root = tmp_path / "case-study"
    root.mkdir()
    files = {
        "dependency-inventory": ("dependencies.txt", b"openai-agents==0.18.3\n"),
        "export": ("reproduction.zip", b"bounded-export-fixture"),
        "minimality-report": ("minimality-report.json", b"{}\n"),
        "original-capsule": ("original.reprosieve", b"original-capsule-fixture"),
        "permission-record": ("permission.json", b'{"publication_approved":true}\n'),
        "predicate": ("predicate.py", b"raise SystemExit(0)\n"),
        "reduced-capsule": ("reduced.reprosieve", b"reduced-capsule-fixture"),
        "reduction-report": ("reduction-report.json", b"{}\n"),
    }
    artifacts: list[dict[str, object]] = []
    for role, (name, content) in files.items():
        path = root / name
        path.write_bytes(content)
        artifacts.append(
            {
                "bytes": len(content),
                "path": name,
                "role": role,
                "sha256": _sha256(path),
            }
        )
    manifest = {
        "artifacts": sorted(artifacts, key=lambda item: str(item["role"])),
        "case_id": "tool-result-2026-001",
        "category": "unexpected-tool-result",
        "environment": {
            "architecture": "x86_64",
            "framework": "OpenAI Agents",
            "framework_version": "0.18.3",
            "operating_system": "linux",
            "python": "3.13.5",
        },
        "execution": {
            "command": ["python", "predicate.py"],
            "expected_exit_code": 0,
            "mode": "offline-predicate-reproduction",
            "what_materialized": ["recorded model and tool values"],
            "what_reexecuted": ["declared failure predicate"],
        },
        "explanation": {
            "failure": "The declared predicate recognizes an unexpected tool result.",
            "limitations": "Permission and disclosure statements require human review.",
            "removed": "Unrelated recorded events and one workspace file.",
            "retained": "The recorded tool result needed by the predicate.",
        },
        "permission": {
            "data_owner_reference": "owner-approved-public-id",
            "disclosure_review_date": "2026-07-25",
            "permission_record": "permission.json",
            "publication_scope": "entire case-study package",
            "reviewer_reference": "maintainer-public-id",
        },
        "schema_version": 1,
        "synthetic": False,
        "title": "Unexpected tool-result failure",
    }
    (root / "case-study.json").write_bytes(canonical_json(manifest))
    return root


def test_permissioned_case_study_package_is_structurally_verified(
    tmp_path: Path,
) -> None:
    root = _case_study(tmp_path)

    report = verify_case_study_package(root)

    assert report == {
        "artifact_count": 8,
        "case_id": "tool-result-2026-001",
        "category": "unexpected-tool-result",
        "execution_mode": "offline-predicate-reproduction",
        "manifest_sha256": _sha256(root / "case-study.json"),
        "permission_measurement": "declared-record-present; human authenticity review required",
        "schema_version": 1,
        "structurally_valid": True,
    }


def test_case_study_rejects_synthetic_content(tmp_path: Path) -> None:
    root = _case_study(tmp_path)
    path = root / "case-study.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["synthetic"] = True
    path.write_bytes(canonical_json(manifest))

    with pytest.raises(ValueError, match="synthetic"):
        verify_case_study_package(root)


def test_case_study_rejects_missing_permission_artifact(tmp_path: Path) -> None:
    root = _case_study(tmp_path)
    path = root / "case-study.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["artifacts"] = [
        item for item in manifest["artifacts"] if item["role"] != "permission-record"
    ]
    path.write_bytes(canonical_json(manifest))

    with pytest.raises(ValueError, match="required artifact roles"):
        verify_case_study_package(root)


def test_case_study_rejects_corrupted_artifact(tmp_path: Path) -> None:
    root = _case_study(tmp_path)
    with (root / "reduced.reprosieve").open("ab") as stream:
        stream.write(b"corruption")

    with pytest.raises(ValueError, match="hash/size"):
        verify_case_study_package(root)


def test_case_study_rejects_unknown_manifest_field(tmp_path: Path) -> None:
    root = _case_study(tmp_path)
    path = root / "case-study.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["permission_verified"] = True
    path.write_bytes(canonical_json(manifest))

    with pytest.raises(ValueError, match="shape"):
        verify_case_study_package(root)


def test_case_study_rejects_uninventoried_file(tmp_path: Path) -> None:
    root = _case_study(tmp_path)
    (root / "not-reviewed.txt").write_text("extra", encoding="utf-8")

    with pytest.raises(ValueError, match="inventory"):
        verify_case_study_package(root)


def test_case_study_rejects_link_like_directory_when_is_symlink_is_false(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _case_study(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = root / "unreviewed-directory"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation is unavailable")
    original_is_symlink = Path.is_symlink

    def junction_like(path: Path) -> bool:
        if path == linked:
            return False
        return original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", junction_like)

    with pytest.raises(ValueError, match="symlink|junction"):
        verify_case_study_package(root)


def test_application_replay_case_requires_application_artifacts(
    tmp_path: Path,
) -> None:
    root = _case_study(tmp_path)
    path = root / "case-study.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["execution"]["mode"] = "application-replay"
    path.write_bytes(canonical_json(manifest))

    with pytest.raises(ValueError, match="required artifact roles"):
        verify_case_study_package(root)


def test_real_case_registry_records_only_external_blockers() -> None:
    registry = json.loads(
        (ROOT / "docs" / "case-studies" / "registry.json").read_text(
            encoding="utf-8"
        )
    )

    assert registry["schema_version"] == 1
    assert registry["cases"] == []
    assert {
        item["category"] for item in registry["external_blockers"]
    } == {
        "application-model-trajectory",
        "serialization-structured-output",
        "unexpected-tool-result",
    }
    assert {
        item["status"] for item in registry["external_blockers"]
    } == {"blocked-external"}
