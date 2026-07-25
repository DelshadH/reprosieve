from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import tempfile
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from scripts.contract import (
    CONTRACT_V2_PREDECESSOR,
    CONTRACT_VERSION_PATH,
    CONTROL_PLANE_FILES,
    assert_commit_exists,
    assert_control_plane_unchanged,
    canonical_json,
    validate_contract_version,
    validate_evidence_window,
    validate_state_shape,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_TIME = "2026-07-25T00:00:00Z"


def _load(name: str) -> dict[str, Any]:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def _documents(progress: dict[str, Any]) -> dict[str, Any]:
    return {
        "project": "runsieve",
        "graph": _load("CODEX_TASKS.json"),
        "progress": progress,
        "registry": _load("GATE_REGISTRY.json"),
        "manual": {"schema_version": 1, "project": "runsieve", "items": []},
    }


def all_pending_state() -> dict[str, Any]:
    graph = _load("CODEX_TASKS.json")
    registry = _load("GATE_REGISTRY.json")
    progress = {
        "schema_version": 1,
        "project": "runsieve",
        "updated_at": FIXTURE_TIME,
        "tasks": {
            task["id"]: {
                "status": "pending",
                "evidence": [],
                "notes": "",
                "blocker_ids": [],
            }
            for task in graph["tasks"]
        },
        "gates": {
            gate["id"]: {"status": "pending", "evidence": []}
            for gate in registry["gates"]
        },
    }
    return {
        "project": "runsieve",
        "graph": graph,
        "progress": progress,
        "registry": registry,
        "manual": {"schema_version": 1, "project": "runsieve", "items": []},
    }


def _evidence_reference(gate: str) -> dict[str, str]:
    return {
        "path": f".evidence/{gate}/contract-self-test/manifest.json",
        "sha256": hashlib.sha256(gate.encode("ascii")).hexdigest(),
    }


def coherent_all_passed_state() -> dict[str, Any]:
    state = all_pending_state()
    tasks = {task["id"]: task for task in state["graph"]["tasks"]}
    for gate_id, gate_state in state["progress"]["gates"].items():
        gate_state["status"] = "passed"
        gate_state["evidence"] = [_evidence_reference(gate_id)]
    for task_id, task_state in state["progress"]["tasks"].items():
        task_state["status"] = "passed"
        task_state["evidence"] = [
            _evidence_reference(gate_id) for gate_id in tasks[task_id]["owns_gates"]
        ]
    return state


def must_reject(
    label: str,
    source: dict[str, Any],
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    candidate = copy.deepcopy(source)
    before = canonical_json(candidate)
    mutate(candidate)
    after = canonical_json(candidate)
    if before == after:
        raise AssertionError(f"contract self-test invalid: {label} mutation made no change")
    try:
        validate_state_shape(**candidate)
    except (TypeError, ValueError):
        return
    raise AssertionError(f"contract self-test failed: accepted {label}")


def _coordinated_delete(state: dict[str, Any]) -> None:
    state["graph"]["tasks"] = [
        task for task in state["graph"]["tasks"] if task["id"] != "RS-080"
    ]
    state["registry"]["gates"] = [
        gate for gate in state["registry"]["gates"] if gate["id"] != "RS-G12"
    ]
    del state["progress"]["tasks"]["RS-080"]
    del state["progress"]["gates"]["RS-G12"]


def _substitute_command(state: dict[str, Any]) -> None:
    state["registry"]["gates"][0]["argv"] = [
        "python",
        "-c",
        "raise SystemExit(0)",
    ]


def _pass_gate_while_owner_pending(state: dict[str, Any]) -> None:
    state["progress"]["gates"]["RS-G13"] = {
        "status": "passed",
        "evidence": [_evidence_reference("RS-G13")],
    }


def _block_without_record(state: dict[str, Any]) -> None:
    task = state["progress"]["tasks"]["RS-000"]
    task["status"] = "blocked"
    task["blocker_ids"] = ["MISSING"]


def _routine_manual(state: dict[str, Any]) -> None:
    state["manual"]["items"].append(
        {
            "id": "HUMAN-001",
            "kind": "architecture_choice",
            "status": "open",
            "reason": "Choose an implementation architecture",
            "why_human_only": "The agent would rather ask",
            "exact_steps": ["Choose"],
            "blocks_tasks": ["RS-000"],
            "blocks_release": True,
            "detected_at": FIXTURE_TIME,
            "probe": {
                "argv": ["false"],
                "exit_code": 1,
                "output_excerpt": "blocked",
            },
            "unblock_check": {"argv": ["false"], "expected_exit_code": 0},
        }
    )


def _malformed_unblock(state: dict[str, Any]) -> None:
    state["manual"]["items"].append(
        {
            "id": "HUMAN-001",
            "kind": "github_authentication",
            "status": "open",
            "reason": "GitHub authentication is unavailable after a concrete CLI probe",
            "why_human_only": "Only the repository owner can authorize publishing identity",
            "exact_steps": ["Run gh auth login"],
            "blocks_tasks": ["RS-080"],
            "blocks_release": True,
            "detected_at": FIXTURE_TIME,
            "probe": {
                "argv": ["gh", "auth", "status"],
                "exit_code": 1,
                "output_excerpt": "not logged in",
            },
            "unblock_check": "gh auth status",
        }
    )


def _duplicate_evidence(state: dict[str, Any]) -> None:
    reference = state["progress"]["gates"]["RS-G01"]["evidence"][0]
    state["progress"]["gates"]["RS-G01"]["evidence"].append(
        copy.deepcopy(reference)
    )


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _initialize_git(root: Path) -> None:
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.name", "RunSieve Contract Self-Test")
    _git(root, "config", "user.email", "contract-self-test@localhost")
    _git(root, "config", "commit.gpgsign", "false")


def _require_nonancestor_rejection() -> None:
    with tempfile.TemporaryDirectory(prefix="runsieve-contract-ancestor-") as raw:
        root = Path(raw)
        _initialize_git(root)
        (root / "first.txt").write_text("first\n", encoding="utf-8")
        _git(root, "add", "first.txt")
        _git(root, "commit", "-m", "first root")
        first = _git(root, "rev-parse", "HEAD")
        _git(root, "switch", "--orphan", "other")
        (root / "second.txt").write_text("second\n", encoding="utf-8")
        _git(root, "add", "second.txt")
        _git(root, "commit", "-m", "other root")
        try:
            assert_commit_exists(root, first, "RS-G01")
        except ValueError as exc:
            if "not an ancestor" in str(exc):
                return
            raise
        raise AssertionError("contract self-test failed: accepted non-ancestor evidence commit")


def _require_changed_control_rejection() -> None:
    with tempfile.TemporaryDirectory(prefix="runsieve-contract-control-") as raw:
        root = Path(raw)
        _initialize_git(root)
        for relative in CONTROL_PLANE_FILES:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if relative == CONTRACT_VERSION_PATH:
                target.write_bytes(
                    canonical_json(
                        {
                            "contract_version": 2,
                            "predecessor_root": CONTRACT_V2_PREDECESSOR,
                            "project": "runsieve",
                            "schema_version": 1,
                        }
                    )
                )
            else:
                target.write_text(f"{relative}\n", encoding="utf-8")
        _git(root, "add", "--all")
        _git(root, "commit", "-m", "contract root")
        (root / "AGENTS.md").write_text("changed\n", encoding="utf-8")
        try:
            assert_control_plane_unchanged(root)
        except ValueError as exc:
            if "differ" in str(exc):
                return
            raise
        raise AssertionError("contract self-test failed: accepted changed immutable file")


def _require_timestamp_rejections() -> None:
    bootstrap = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    now = bootstrap + timedelta(hours=1)
    invalid = (
        {
            "proof_started": bootstrap - timedelta(microseconds=1),
            "proof_finished": bootstrap,
            "message": "predates",
        },
        {
            "proof_started": bootstrap,
            "proof_finished": now + timedelta(minutes=6),
            "message": "future",
        },
    )
    for case in invalid:
        try:
            validate_evidence_window(
                bootstrap=bootstrap,
                proof_started=case["proof_started"],
                proof_finished=case["proof_finished"],
                deadline_hour=2,
                now=now,
                label="RS-G01",
            )
        except ValueError as exc:
            if case["message"] in str(exc):
                continue
            raise
        raise AssertionError(
            f"contract self-test failed: accepted {case['message']} evidence timestamp"
        )


def run_contract_self_tests(live_progress: dict[str, Any]) -> None:
    version = _load(CONTRACT_VERSION_PATH)
    validate_contract_version(version)
    validate_state_shape(**_documents(live_progress))
    pending = all_pending_state()
    passed = coherent_all_passed_state()
    validate_state_shape(**pending)
    validate_state_shape(**passed)

    must_reject("deleted gates", pending, lambda state: state["progress"].__setitem__("gates", {}))
    must_reject("deleted tasks", pending, lambda state: state["progress"].__setitem__("tasks", {}))
    must_reject(
        "extra task",
        pending,
        lambda state: state["progress"]["tasks"].__setitem__(
            "RS-999",
            {"status": "pending", "evidence": [], "notes": "", "blocker_ids": []},
        ),
    )
    must_reject(
        "extra gate",
        pending,
        lambda state: state["progress"]["gates"].__setitem__(
            "RS-G99", {"status": "pending", "evidence": []}
        ),
    )
    must_reject(
        "task gate ownership deletion",
        pending,
        lambda state: state["graph"]["tasks"][1].__setitem__("owns_gates", []),
    )
    must_reject(
        "gate owner deletion",
        pending,
        lambda state: state["registry"]["gates"][0].__setitem__("owner_task", ""),
    )
    must_reject("coordinated contract deletion", pending, _coordinated_delete)
    must_reject(
        "one-byte task mutation",
        pending,
        lambda state: state["graph"]["tasks"][0].__setitem__(
            "objective", state["graph"]["tasks"][0]["objective"] + "!"
        ),
    )
    must_reject(
        "one-key registry mutation",
        pending,
        lambda state: state["registry"].__setitem__("unexpected", True),
    )
    must_reject("registry command substitution", pending, _substitute_command)
    must_reject(
        "required assertion deletion",
        pending,
        lambda state: state["registry"]["gates"][0]["required_assertions"].pop(),
    )
    must_reject(
        "deadline extension",
        pending,
        lambda state: state["graph"]["tasks"][0].__setitem__("deadline_hour", 999),
    )
    must_reject(
        "unknown status",
        pending,
        lambda state: state["progress"]["tasks"]["RS-000"].__setitem__("status", "done"),
    )
    must_reject(
        "task passed while owned gate pending",
        pending,
        lambda state: state["progress"]["tasks"]["RS-000"].__setitem__("status", "passed"),
    )
    must_reject("gate passed while owner pending", pending, _pass_gate_while_owner_pending)
    must_reject(
        "downstream task progress before dependencies",
        pending,
        lambda state: state["progress"]["tasks"]["RS-010"].__setitem__(
            "status", "in_progress"
        ),
    )
    must_reject(
        "gate in progress before owner",
        pending,
        lambda state: state["progress"]["gates"]["RS-G13"].__setitem__(
            "status", "in_progress"
        ),
    )
    must_reject(
        "multiple simultaneous in-progress tasks",
        pending,
        lambda state: (
            state["progress"]["tasks"]["RS-000"].__setitem__("status", "in_progress"),
            state["progress"]["tasks"]["RS-010"].__setitem__("status", "in_progress"),
        ),
    )
    must_reject("duplicate evidence references", passed, _duplicate_evidence)
    must_reject("blocked task without manual record", pending, _block_without_record)
    must_reject("routine engineering disguised as manual work", pending, _routine_manual)
    must_reject("non-executable unblock check", pending, _malformed_unblock)

    try:
        must_reject("intentional no-op guard probe", pending, lambda state: None)
    except AssertionError as exc:
        if "made no change" not in str(exc):
            raise
    else:
        raise AssertionError("contract self-test failed: no-op mutation guard did not fire")

    for bad in (
        "/tmp/manifest.json",
        "../manifest.json",
        ".evidence\\RS-G01\\manifest.json",
        ".evidence/RS-G01/../manifest.json",
    ):
        changed = copy.deepcopy(passed)
        changed["progress"]["gates"]["RS-G01"]["evidence"][0]["path"] = bad
        try:
            validate_state_shape(**changed)
        except ValueError:
            continue
        raise AssertionError(f"contract self-test failed: accepted unsafe path {bad}")

    for invalid_version in (
        {},
        {
            "contract_version": 1,
            "predecessor_root": CONTRACT_V2_PREDECESSOR,
            "project": "runsieve",
            "schema_version": 1,
        },
        {**version, "unknown": True},
    ):
        try:
            validate_contract_version(invalid_version)
        except ValueError:
            continue
        raise AssertionError("contract self-test failed: accepted invalid contract identity")

    _require_timestamp_rejections()
    _require_nonancestor_rejection()
    _require_changed_control_rejection()


def main() -> int:
    run_contract_self_tests(_load("PROGRESS.json"))
    print(
        "RunSieve contract-v2 self-tests passed: explicit pending/passed fixtures, "
        "no-op mutation guard, exact identity, ancestry, timestamps, ownership, "
        "evidence references, blockers, and immutable control changes are checked."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
