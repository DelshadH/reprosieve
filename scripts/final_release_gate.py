from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from scripts.evidence import write_canonical_json

ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r"^[0-9a-f]{40}$")
COMMANDS = (
    ("verify", (sys.executable, "-m", "scripts.verify"), 360),
    ("security", (sys.executable, "scripts/security_check.py"), 120),
    ("secrets", (sys.executable, "scripts/detect_secrets_check.py"), 120),
    ("killer-demo", (sys.executable, "scripts/killer_demo.py"), 30),
    ("minimality-oracle", (sys.executable, "-m", "scripts.minimality_oracle_proof"), 30),
)


def _head() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    value = completed.stdout.strip()
    if completed.returncode or SHA.fullmatch(value) is None:
        raise RuntimeError("final release gate cannot resolve HEAD")
    return value


def _require_clean() -> None:
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if completed.returncode or completed.stdout:
        raise RuntimeError("final release gate requires a clean exact-head checkout")


def run_final_gate() -> dict[str, object]:
    _require_clean()
    commit = _head()
    requested = os.environ.get("RUNSIEVE_EVIDENCE_COMMIT")
    if requested is not None and requested != commit:
        raise RuntimeError("final release gate checkout differs from requested commit")
    results: list[dict[str, object]] = []
    for name, argv, timeout in COMMANDS:
        completed = subprocess.run(
            argv,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
        if completed.returncode:
            raise RuntimeError(f"final release check failed: {name}")
        results.append(
            {
                "id": name,
                "passed": True,
                "stderr_sha256": hashlib.sha256(completed.stderr).hexdigest(),
                "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(),
            }
        )
    _require_clean()
    return {
        "checks": results,
        "commit": commit,
        "gate": "runsieve-final-alpha-candidate",
        "passed": True,
        "schema_version": 1,
    }


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) not in {0, 2} or (arguments and arguments[0] != "--output"):
        print(
            "usage: python -m scripts.final_release_gate [--output FILE]",
            file=sys.stderr,
        )
        return 2
    try:
        report = run_final_gate()
        if arguments:
            output = Path(arguments[1])
            if output.exists() or output.is_symlink():
                raise FileExistsError("final release receipt already exists")
            write_canonical_json(output, report)
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as error:
        print(f"final release gate failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
