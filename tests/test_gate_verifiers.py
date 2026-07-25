from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_tri_state_gate_runs_its_real_proof_and_reports_registered_assertions(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"gate":"RS-G07"}\n', encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, "-m", "scripts.gates.RS_G07", str(manifest)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["gate"] == "RS-G07"
    assert report["passed"] is True
    assert {item["id"] for item in report["assertions"]} == {
        "reproduces-distinct",
        "absent-distinct",
        "invalid-distinct",
        "timeout-invalid",
        "signal-invalid",
    }
