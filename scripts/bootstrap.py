from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.contract import assert_control_plane_unchanged, validate_execution_state

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / ".agent-state.json"
PROGRESS_PATH = ROOT / "PROGRESS.json"


def run(*argv: str, capture: bool = True) -> str:
    result = subprocess.run(argv, cwd=ROOT, text=True, capture_output=capture, check=False)
    if result.returncode:
        output = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"{' '.join(argv)} failed: {output}")
    return result.stdout.strip() if capture else ""


def probe(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=ROOT, text=True, capture_output=True, check=False)


def main() -> int:
    top = probe("git", "rev-parse", "--show-toplevel")
    if top.returncode:
        run("git", "init", "-b", "main")
    elif Path(top.stdout.strip()).resolve() != ROOT:
        raise RuntimeError("RunSieve must be opened as its own repository root, not inside a parent Git repository")
    name = probe("git", "config", "--get", "user.name")
    if name.returncode or not name.stdout.strip():
        run("git", "config", "user.name", "RunSieve Build Agent")
    email = probe("git", "config", "--get", "user.email")
    if email.returncode or not email.stdout.strip():
        run("git", "config", "user.email", "runsieve-agent@localhost")
    run("git", "config", "commit.gpgsign", "false")

    has_head = probe("git", "rev-parse", "--verify", "HEAD").returncode == 0
    if not has_head:
        if STATE_PATH.exists():
            raise RuntimeError("unexpected pre-existing .agent-state.json; start from a clean skeleton so the deadline anchor cannot be reused")
        state = {"schema_version": 1, "project": "runsieve", "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
        validate_execution_state(state, "runsieve")
        STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        progress = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
        progress["updated_at"] = state["started_at"]
        PROGRESS_PATH.write_text(json.dumps(progress, indent=2) + "\n", encoding="utf-8")
        run("git", "add", "--all")
        run("git", "commit", "-m", "chore: anchor RunSieve autonomous build contract and execution clock")
    else:
        if not STATE_PATH.exists():
            raise RuntimeError("existing repository is missing its immutable .agent-state.json; restart from the untouched skeleton instead of resetting the deadline")
        validate_execution_state(json.loads(STATE_PATH.read_text(encoding="utf-8")), "runsieve")
    assert_control_plane_unchanged(ROOT)

    verify = subprocess.run([sys.executable, "-m", "scripts.verify"], cwd=ROOT, check=False)
    if verify.returncode:
        return verify.returncode
    next_task = subprocess.run([sys.executable, "-m", "scripts.next_task"], cwd=ROOT, check=False)
    if next_task.returncode:
        return next_task.returncode
    print("RunSieve bootstrap complete. Continue the autonomous loop; no user action is required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
