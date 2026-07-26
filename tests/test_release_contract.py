from __future__ import annotations

import subprocess
import sys
import time
import tomllib
from pathlib import Path

import runsieve
from runsieve.fixtures import killer_capsule

ROOT = Path(__file__).resolve().parents[1]


def test_ci_declares_supported_python_and_portable_reproduction_matrix() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for version in ('"3.11"', '"3.12"', '"3.13"'):
        assert version in workflow
    assert "ubuntu-latest" in workflow
    assert "macos-latest" in workflow
    assert "persist-credentials: false" in workflow
    assert "Smoke-test wheel without source tree" in workflow
    assert "scripts.portable_reproduction_proof" in workflow
    assert "scripts.generate_gate_evidence" in workflow
    assert "RS-G10" in workflow
    assert "scripts.package_matrix_proof" in workflow
    assert "RS-G13" in workflow
    assert "rs-g13-evidence" in workflow
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
    assert "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c" in workflow


def test_every_ci_checkout_uses_the_exact_evidence_commit() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    checkout = "uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
    exact_ref = "ref: ${{ env.RUNSIEVE_EVIDENCE_COMMIT }}"

    assert workflow.count(checkout) > 0
    assert workflow.count(exact_ref) == workflow.count(checkout)


def test_package_identifies_as_the_first_0_1_alpha_without_broad_replay_claims() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").lower()

    assert metadata["project"]["version"] == "0.1.0a1"
    assert runsieve.__version__ == "0.1.0a1"
    assert "hermetic" not in changelog
    assert "recorded-output replay" not in changelog


def test_release_workflow_attests_the_reproducibility_checked_artifacts() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "RUNSIEVE_EVIDENCE_COMMIT: ${{ github.sha }}" in workflow
    assert "ref: ${{ env.RUNSIEVE_EVIDENCE_COMMIT }}" in workflow
    assert "python -m scripts.package_matrix_proof" in workflow
    assert 'subject-path: "release-proof/runsieve-*"' in workflow
    assert "release-proof/*" in workflow


def test_killer_demo_completes_the_full_claim_within_twenty_seconds() -> None:
    started = time.monotonic()
    completed = subprocess.run(
        [sys.executable, "scripts/killer_demo.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    duration = time.monotonic() - started
    assert completed.returncode == 0, completed.stderr
    assert "reduced 247 events to 5; 1-minimal" in completed.stdout
    assert "wrote deterministic recorded-output materialization" in completed.stdout
    assert '"result":"reproduces"' in completed.stdout
    assert "exported one-command offline issue reproduction" in completed.stdout
    assert duration <= 20


def test_cli_help_starts_without_the_optional_sdk_imported() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "runsieve.cli", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "capture" in completed.stdout
    assert "reduce" in completed.stdout
    assert "materialize" in completed.stdout
    assert "reproduce-predicate" in completed.stdout


def test_public_fixture_is_explicitly_synthetic_and_uses_recorded_values() -> None:
    capsule = killer_capsule()
    assert capsule.metadata["fixture_kind"] == "synthetic"
    assert "application_replay" not in capsule.metadata
    predicate = capsule.workspace["verify_failure.py"]
    assert "RUNSIEVE_REPLAY" in predicate
    assert "RUNSIEVE_APPLICATION_RESULT" not in predicate


def test_repository_contains_the_required_release_support_surface() -> None:
    required = (
        "LICENSE",
        "SECURITY.md",
        "SUPPORT.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "CHANGELOG.md",
        ".github/ISSUE_TEMPLATE/bug-report.yml",
        ".github/ISSUE_TEMPLATE/reproduction-failure.yml",
    )

    assert [path for path in required if not (ROOT / path).is_file()] == []
