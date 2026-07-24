from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

from runsieve.capsule import write_capsule
from runsieve.cli import main
from runsieve.fixtures import killer_capsule


def run() -> int:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="runsieve-demo-") as temporary:
        root = Path(temporary)
        source = root / "source.runsieve"
        reduced = root / "reduced"
        reduced.mkdir()
        write_capsule(killer_capsule(), source)
        if main(
            [
                "minimize",
                str(source),
                "--output-dir",
                str(reduced),
                "--timeout",
                "3",
                "--predicate",
                "python",
                "verify_failure.py",
            ]
        ):
            return 1
        artifact = next(reduced.glob("*.runsieve"))
        export = root / "issue-repro"
        if main(["export", str(artifact), "--output", str(export)]):
            return 1
        proof = subprocess.run(
            [sys.executable, "reproduce.py"],
            cwd=export,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proof.returncode != 0:
            return 1
    elapsed = time.monotonic() - started
    if elapsed > 20:
        print(f"killer demo exceeded 20 seconds: {elapsed:.3f}s", file=sys.stderr)
        return 1
    print(f"killer demo passed in {elapsed:.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
