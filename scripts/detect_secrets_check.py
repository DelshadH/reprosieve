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


FindingIdentity = tuple[str, str, str]


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def _reviewed_findings(baseline: object) -> set[FindingIdentity]:
    if not isinstance(baseline, dict):
        raise ValueError("detect-secrets baseline is missing or invalid")
    results = baseline.get("results")
    if not isinstance(results, dict) or not results:
        raise ValueError("detect-secrets baseline has no reviewed findings")
    reviewed: set[FindingIdentity] = set()
    for path, findings in results.items():
        if not isinstance(path, str) or not isinstance(findings, list):
            raise ValueError("detect-secrets baseline contains unaudited findings")
        for finding in findings:
            if (
                not isinstance(finding, dict)
                or finding.get("is_secret") is not False
                or not isinstance(finding.get("type"), str)
                or not isinstance(finding.get("hashed_secret"), str)
            ):
                raise ValueError(
                    "detect-secrets baseline contains unaudited findings"
                )
            reviewed.add(
                (
                    _normalize_path(path),
                    finding["type"],
                    finding["hashed_secret"],
                )
            )
    return reviewed


def _reviewed_baseline() -> set[FindingIdentity]:
    try:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("detect-secrets baseline is missing or invalid") from error
    return _reviewed_findings(baseline)


def _hook_command() -> list[str]:
    name = "detect-secrets-hook.exe" if os.name == "nt" else "detect-secrets-hook"
    executable = Path(sys.executable).with_name(name)
    if not executable.is_file():
        raise ValueError("detect-secrets-hook is not installed beside this Python")
    return [
        str(executable),
        "--no-verify",
        "--json",
        "--exclude-files",
        EXCLUDED,
    ]


def check_files(files: list[str]) -> int:
    try:
        reviewed = _reviewed_baseline()
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
            unreviewed: set[str] = set()
            for path, findings in results.items():
                if not isinstance(path, str) or not isinstance(findings, list):
                    print(
                        "detect-secrets-hook returned an invalid report",
                        file=sys.stderr,
                    )
                    return 1
                for finding in findings:
                    identity = (
                        _normalize_path(path),
                        finding.get("type") if isinstance(finding, dict) else "",
                        (
                            finding.get("hashed_secret")
                            if isinstance(finding, dict)
                            else ""
                        ),
                    )
                    if identity not in reviewed:
                        unreviewed.add(path)
            if unreviewed:
                for path in sorted(unreviewed):
                    print(
                        f"{path}: new detect-secrets finding",
                        file=sys.stderr,
                    )
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
