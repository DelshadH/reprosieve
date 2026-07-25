from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def support_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def verify_gate(
    *,
    gate: str,
    assertions: tuple[str, ...],
    pytest_nodes: tuple[str, ...],
    expected_support_sha256: str,
) -> int:
    if len(sys.argv) != 2:
        print(f"{gate}: expected one evidence-manifest path", file=sys.stderr)
        return 2
    try:
        manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"{gate}: invalid evidence manifest: {error}", file=sys.stderr)
        return 2
    if not isinstance(manifest, dict) or manifest.get("gate") != gate:
        print(f"{gate}: evidence manifest identity mismatch", file=sys.stderr)
        return 2
    if support_sha256() != expected_support_sha256:
        print(f"{gate}: verifier support implementation changed", file=sys.stderr)
        return 2
    if not assertions or len(assertions) != len(set(assertions)) or not pytest_nodes:
        print(f"{gate}: verifier specification is invalid", file=sys.stderr)
        return 2

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + environment.get(
        "PYTHONPATH", ""
    )
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *pytest_nodes],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if completed.returncode:
        print(completed.stdout, file=sys.stderr, end="")
        print(completed.stderr, file=sys.stderr, end="")
        return completed.returncode

    report = {
        "assertions": [{"id": assertion, "passed": True} for assertion in assertions],
        "gate": gate,
        "passed": True,
    }
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0
