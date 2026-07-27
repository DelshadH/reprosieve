from __future__ import annotations

import json
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import reprosieve
from reprosieve.fixtures import killer_capsule

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

    assert metadata["project"]["name"] == "reprosieve"
    assert metadata["project"]["scripts"] == {"reprosieve": "reprosieve.cli:main"}
    assert metadata["project"]["version"] == "0.1.0a1"
    assert metadata["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == [
        "src/reprosieve"
    ]
    assert metadata["tool"]["hatch"]["build"]["targets"]["sdist"]["include"][0] == (
        "/src/reprosieve"
    )
    assert reprosieve.__version__ == "0.1.0a1"
    assert "hermetic" not in changelog
    assert "recorded-output replay" not in changelog


def test_release_workflow_attests_the_reproducibility_checked_artifacts() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "RUNSIEVE_EVIDENCE_COMMIT: ${{ github.sha }}" in workflow
    assert "ref: ${{ env.RUNSIEVE_EVIDENCE_COMMIT }}" in workflow
    assert 'tags:\n      - "v0.1.0a1"' in workflow
    assert "scripts.release_preflight" in workflow
    assert "python -m scripts.package_matrix_proof" in workflow
    assert "release-proof/reprosieve-*.whl" in workflow
    assert "release-proof/reprosieve-*.tar.gz" in workflow
    assert "release-proof/SHA256SUMS" in workflow
    assert "release-proof/reprosieve.spdx.json" in workflow
    assert "release-proof/*" in workflow
    assert "environment: pypi" in workflow
    assert "pypa/gh-action-pypi-publish@ba38be9e461d3875417946c167d0b5f3d385a247" in workflow
    assert workflow.count("id-token: write") == 2
    publish = workflow.split("publish-pypi:", 1)[1]
    assert "actions/checkout@" not in publish
    assert "gh attestation verify" in publish
    build = workflow.split("build-and-attest:", 1)[1].split("publish-pypi:", 1)[0]
    assert "--workflow final-evidence.yml" in build
    assert "--commit \"$RUNSIEVE_EVIDENCE_COMMIT\"" in build
    assert "final-decision-receipt" in build
    assert "scripts.verify_final_receipt" in build


def test_release_preflight_tag_matches_project_version() -> None:
    from scripts.release_preflight import expected_tag

    assert expected_tag() == "v0.1.0a1"


def test_final_evidence_workflow_is_exact_head_and_attestation_bound() -> None:
    workflow = (ROOT / ".github" / "workflows" / "final-evidence.yml").read_text(
        encoding="utf-8"
    )
    assert "workflow_dispatch:" in workflow
    assert "RUNSIEVE_EVIDENCE_COMMIT: ${{ inputs.commit }}" in workflow
    assert workflow.count("ref: ${{ env.RUNSIEVE_EVIDENCE_COMMIT }}") >= 5
    assert "python -m scripts.final_release_gate" in workflow
    assert "scripts.package_matrix_proof" in workflow
    assert "scripts.portable_reproduction_proof" in workflow
    assert "scripts.verify_application_replay_evidence" in workflow
    assert "gh attestation verify" in workflow
    assert "final-decision-receipt" in workflow


def test_final_release_gate_declares_current_exact_head_checks() -> None:
    from scripts.final_release_gate import COMMANDS

    assert [name for name, _argv, _timeout in COMMANDS] == [
        "verify",
        "security",
        "secrets",
        "killer-demo",
        "minimality-oracle",
    ]


def test_readme_uses_the_current_final_release_gate() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "python -m scripts.final_release_gate" in readme
    assert "python -m scripts.release_gate" not in readme


def test_final_receipt_rejects_a_different_commit(tmp_path: Path) -> None:
    from scripts.verify_final_receipt import verify_receipt

    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "commit": "a" * 40,
                "gate": "final-release-evidence",
                "passed": True,
                "workflow_run": "123-1",
            }
        ),
        encoding="utf-8",
    )
    assert verify_receipt(receipt, expected_commit="a" * 40)["passed"] is True
    try:
        verify_receipt(receipt, expected_commit="b" * 40)
    except ValueError as error:
        assert "expected commit" in str(error)
    else:
        raise AssertionError("mismatched final-evidence receipt was accepted")


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
        [sys.executable, "-m", "reprosieve.cli", "--help"],
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
