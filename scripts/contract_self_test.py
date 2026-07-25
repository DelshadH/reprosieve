from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.contract import normalized_relative_path, validate_state_shape

ROOT = Path(__file__).resolve().parents[1]
BASE = {
    "project": "runsieve",
    "graph": json.loads((ROOT / "CODEX_TASKS.json").read_text(encoding="utf-8")),
    "progress": json.loads((ROOT / "PROGRESS.json").read_text(encoding="utf-8")),
    "registry": json.loads((ROOT / "GATE_REGISTRY.json").read_text(encoding="utf-8")),
    "manual": json.loads((ROOT / "MANUAL_REQUIRED.json").read_text(encoding="utf-8")),
}

def must_reject(label: str, mutate: object) -> None:
    candidate = copy.deepcopy(BASE)
    mutate(candidate)  # type: ignore[operator]
    try:
        validate_state_shape(**candidate)
    except (TypeError, ValueError):
        return
    raise AssertionError(f"contract self-test failed: accepted {label}")

validate_state_shape(**BASE)
must_reject("deleted gates", lambda state: state["progress"].__setitem__("gates", {}))
must_reject("deleted tasks", lambda state: state["progress"].__setitem__("tasks", {}))
must_reject("extra gate", lambda state: state["progress"]["gates"].__setitem__("RS-G99", {"status": "passed", "evidence": []}))
def coordinated_delete(state: dict[str, object]) -> None:
    state["graph"]["tasks"] = [task for task in state["graph"]["tasks"] if task["id"] != "RS-080"]  # type: ignore[index]
    state["registry"]["gates"] = [gate for gate in state["registry"]["gates"] if gate["id"] != "RS-G12"]  # type: ignore[index]
    del state["progress"]["tasks"]["RS-080"]  # type: ignore[index]
    del state["progress"]["gates"]["RS-G12"]  # type: ignore[index]
must_reject("coordinated contract deletion", coordinated_delete)
def substitute_command(state: dict[str, object]) -> None:
    state["registry"]["gates"][0]["argv"] = ["python", "-c", "raise SystemExit(0)"]  # type: ignore[index]
must_reject("registry command substitution", substitute_command)
must_reject("required assertion deletion", lambda state: state["registry"]["gates"][0]["required_assertions"].pop())
must_reject("deadline extension", lambda state: state["graph"]["tasks"][0].__setitem__("deadline_hour", 999))
must_reject("unknown status", lambda state: state["progress"]["tasks"]["RS-000"].__setitem__("status", "done"))
must_reject("task pass without gate pass", lambda state: state["progress"]["tasks"]["RS-000"].__setitem__("status", "passed"))
must_reject("gate active before owner", lambda state: state["progress"]["gates"]["RS-G13"].__setitem__("status", "in_progress"))
must_reject("missing ownership", lambda state: state["graph"]["tasks"][1].__setitem__("owns_gates", []))
def block_without_record(state: dict[str, object]) -> None:
    task = state["progress"]["tasks"]["RS-000"]  # type: ignore[index]
    task["status"] = "blocked"
    task["blocker_ids"] = ["MISSING"]
must_reject("blocked task without manual record", block_without_record)
def routine_manual(state: dict[str, object]) -> None:
    state["manual"]["items"].append({"id": "HUMAN-001", "kind": "architecture_choice", "status": "open", "reason": "Choose an implementation architecture", "why_human_only": "The agent would rather ask", "exact_steps": ["Choose"], "blocks_tasks": ["RS-000"], "blocks_release": True, "detected_at": "2026-07-24T00:00:00Z", "probe": {"argv": ["false"], "exit_code": 1, "output_excerpt": "blocked"}, "unblock_check": {"argv": ["false"], "expected_exit_code": 0}})  # type: ignore[index]
must_reject("routine engineering disguised as manual work", routine_manual)
def malformed_unblock(state: dict[str, object]) -> None:
    state["manual"]["items"].append({"id": "HUMAN-001", "kind": "github_authentication", "status": "open", "reason": "GitHub authentication is unavailable after a concrete CLI probe", "why_human_only": "Only the repository owner can authorize the publishing identity", "exact_steps": ["Run gh auth login"], "blocks_tasks": ["RS-080"], "blocks_release": True, "detected_at": "2026-07-24T00:00:00Z", "probe": {"argv": ["gh", "auth", "status"], "exit_code": 1, "output_excerpt": "not logged in"}, "unblock_check": "gh auth status"})  # type: ignore[index]
must_reject("non-executable unblock check", malformed_unblock)
for bad in ["/tmp/manifest.json", "../manifest.json", ".evidence\\RS-G01\\manifest.json", ".evidence/RS-G01/../manifest.json"]:
    try:
        normalized_relative_path(bad)
    except ValueError:
        continue
    raise AssertionError(f"contract self-test failed: accepted unsafe path {bad}")
print("RunSieve contract self-tests passed: set deletion, verifier substitution, assertion removal, ungated task completion, blocker, and unsafe-path bypasses are rejected.")
