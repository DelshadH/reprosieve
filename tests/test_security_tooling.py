from __future__ import annotations

import json
from pathlib import Path

from scripts.detect_secrets_check import check_files


def test_detect_secrets_baseline_is_explicitly_reviewed() -> None:
    baseline = json.loads(Path(".secrets.baseline").read_text(encoding="utf-8"))
    findings = [
        finding
        for path_findings in baseline["results"].values()
        for finding in path_findings
    ]
    assert findings
    assert all(finding.get("is_secret") is False for finding in findings)


def test_detect_secrets_check_rejects_a_new_synthetic_finding(tmp_path: Path) -> None:
    candidate = tmp_path / "new_finding.py"
    candidate.write_text(
        'password = "RUNSIEVE-SYNTHETIC-CREDENTIAL-CANARY"\n',
        encoding="utf-8",
    )
    assert check_files([str(candidate)]) == 1
