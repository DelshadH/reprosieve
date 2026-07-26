from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("agents", reason="openai extra is required for application replay")

from scripts.generate_application_replay_evidence import generate_evidence
from scripts.verify_application_replay_evidence import (
    verify_evidence,
    verify_evidence_tracked_in_head,
    write_verification_attestation,
)

ROOT = Path(__file__).resolve().parents[1]


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        text=True,
        capture_output=True,
        check=True,
    )
    return completed.stdout.strip()


def test_application_replay_evidence_capsules_are_not_ignored() -> None:
    completed = subprocess.run(
        [
            "git",
            "check-ignore",
            "--no-index",
            ".evidence/RS-05-AR1/fixture/source.runsieve",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 1, completed.stdout


def test_independent_application_replay_evidence_verifier(tmp_path: Path) -> None:
    commit = "a" * 40
    evidence = tmp_path / "application-replay-evidence"
    reference = generate_evidence(evidence, commit=commit)

    report = verify_evidence(evidence, expected_commit=commit)

    assert reference["path"] == "evidence.json"
    assert report == {
        "assertions": [
            {"id": "application-executed", "passed": True},
            {"id": "all-interactions-consumed", "passed": True},
            {"id": "provider-canary-zero", "passed": True},
            {"id": "original-tool-canary-zero", "passed": True},
            {"id": "instruction-divergence", "passed": True},
            {"id": "input-divergence", "passed": True},
            {"id": "tool-schema-divergence", "passed": True},
            {"id": "argument-divergence", "passed": True},
            {"id": "ordering-divergence", "passed": True},
            {"id": "early-exit-divergence", "passed": True},
            {"id": "unsupported-surface-rejected", "passed": True},
            {"id": "caught-original-tool-attempt-rejected", "passed": True},
            {"id": "real-unit-reduced", "passed": True},
            {"id": "independent-one-minimal", "passed": True},
        ],
        "commit": commit,
        "gate": "RS-05-AR1",
        "passed": True,
        "schema_version": 1,
    }
    attestation_path = evidence / "verification.json"
    attestation = write_verification_attestation(
        evidence,
        expected_commit=commit,
        output=attestation_path,
    )
    assert attestation["evidence_manifest"]["path"] == "evidence.json"
    assert attestation["verifier"]["path"] == "scripts/verify_application_replay_evidence.py"
    assert attestation_path.is_file()


def test_application_replay_evidence_rejects_corrupted_artifact(tmp_path: Path) -> None:
    commit = "b" * 40
    evidence = tmp_path / "application-replay-evidence"
    generate_evidence(evidence, commit=commit)
    manifest = json.loads((evidence / "evidence.json").read_text(encoding="utf-8"))
    reduced = next(
        item["path"]
        for item in manifest["artifacts"]
        if item["role"] == "reduced-capsule"
    )
    with (evidence / reduced).open("ab") as stream:
        stream.write(b"corruption")

    with pytest.raises(ValueError, match="hash/size mismatch"):
        verify_evidence(evidence, expected_commit=commit)


def test_application_replay_evidence_rejects_wrong_commit(tmp_path: Path) -> None:
    evidence = tmp_path / "application-replay-evidence"
    generate_evidence(evidence, commit="c" * 40)

    with pytest.raises(ValueError, match="commit"):
        verify_evidence(evidence, expected_commit="d" * 40)


def test_application_replay_evidence_must_be_committed_in_head(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    scripts = repository / "scripts"
    scripts.mkdir(parents=True)
    for name in (
        "generate_application_replay_evidence.py",
        "verify_application_replay_evidence.py",
    ):
        shutil.copyfile(ROOT / "scripts" / name, scripts / name)
    _git(repository, "init", "--initial-branch=main")
    _git(repository, "config", "user.email", "runsieve@example.invalid")
    _git(repository, "config", "user.name", "RunSieve test")
    _git(repository, "add", "scripts")
    _git(repository, "commit", "-m", "implementation")
    implementation_commit = _git(repository, "rev-parse", "HEAD")

    evidence = repository / ".evidence" / "RS-05-AR1" / "fixture"
    evidence.parent.mkdir(parents=True)
    generate_evidence(evidence, commit=implementation_commit)
    write_verification_attestation(
        evidence,
        expected_commit=implementation_commit,
        output=evidence / "verification.json",
    )

    with pytest.raises(ValueError, match="not tracked in HEAD"):
        verify_evidence_tracked_in_head(
            evidence,
            expected_commit=implementation_commit,
            repo_root=repository,
        )

    _git(repository, "add", ".evidence")
    _git(repository, "commit", "-m", "register evidence")
    report = verify_evidence_tracked_in_head(
        evidence,
        expected_commit=implementation_commit,
        repo_root=repository,
    )
    assert report["passed"] is True
