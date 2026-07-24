from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = (
    r"(^|[\\/])("
    r"\.git|\.venv|\.test-env|\.evidence|dist|"
    r"\.mypy_cache|\.pytest_cache|\.ruff_cache"
    r")([\\/]|$)"
)


def main() -> int:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "detect_secrets",
            "scan",
            "--all-files",
            "--exclude-files",
            EXCLUDED,
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(completed.stdout)
    results = report.get("results")
    if not isinstance(results, dict):
        print("detect-secrets returned an invalid report", file=sys.stderr)
        return 1
    findings = sum(len(items) for items in results.values() if isinstance(items, list))
    if findings:
        for path in sorted(results):
            print(f"{path}: detect-secrets finding", file=sys.stderr)
        return 1
    print("detect-secrets scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
