from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / ".secrets.baseline"
EXCLUDED = (
    r"(^|[\\/])("
    r"\.git|\.venv|\.test-env|\.evidence|\.secrets\.baseline|dist|"
    r"\.mypy_cache|\.pytest_cache|\.ruff_cache"
    r")([\\/]|$)"
)
_BATCH_SIZE = 50


def _reviewed_baseline() -> None:
    try:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("detect-secrets baseline is missing or invalid") from error
    results = baseline.get("results") if isinstance(baseline, dict) else None
    if not isinstance(results, dict) or not results:
        raise ValueError("detect-secrets baseline has no reviewed findings")
    for findings in results.values():
        if not isinstance(findings, list) or any(
            not isinstance(finding, dict) or finding.get("is_secret") is not False
            for finding in findings
        ):
            raise ValueError("detect-secrets baseline contains unaudited findings")


def _hook_command() -> list[str]:
    name = "detect-secrets-hook.exe" if os.name == "nt" else "detect-secrets-hook"
    executable = Path(sys.executable).with_name(name)
    if not executable.is_file():
        raise ValueError("detect-secrets-hook is not installed beside this Python")
    return [
        str(executable),
        "--baseline",
        BASELINE.relative_to(ROOT).as_posix(),
        "--no-verify",
        "--json",
        "--exclude-files",
        EXCLUDED,
    ]


def check_files(files: list[str]) -> int:
    try:
        _reviewed_baseline()
        command = _hook_command()
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    selected = [path for path in files if path]
    for offset in range(0, len(selected), _BATCH_SIZE):
        batch = selected[offset : offset + _BATCH_SIZE]
        completed = subprocess.run(
            [*command, *batch],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            try:
                report = json.loads(completed.stdout)
            except json.JSONDecodeError:
                print("detect-secrets-hook returned an invalid report", file=sys.stderr)
                return 1
            results = report.get("results") if isinstance(report, dict) else None
            if not isinstance(results, dict) or not results:
                print("detect-secrets-hook failed without findings", file=sys.stderr)
                return 1
            for path in sorted(results):
                print(f"{path}: new detect-secrets finding", file=sys.stderr)
            return 1
    return 0


def _repository_files() -> list[str]:
    completed = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if completed.returncode:
        raise ValueError("detect-secrets could not enumerate repository files")
    return [
        path.decode("utf-8")
        for path in completed.stdout.split(b"\0")
        if path
    ]


def main() -> int:
    try:
        files = _repository_files()
    except (UnicodeDecodeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    if check_files(files):
        return 1
    print("detect-secrets reviewed-baseline check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
