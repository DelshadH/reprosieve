from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ci_declares_supported_python_and_portable_reproduction_matrix() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for version in ('"3.11"', '"3.12"', '"3.13"'):
        assert version in workflow
    assert "ubuntu-latest" in workflow
    assert "macos-latest" in workflow
    assert "persist-credentials: false" in workflow
    assert "Smoke-test wheel without source tree" in workflow


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
    assert "minimize" in completed.stdout
