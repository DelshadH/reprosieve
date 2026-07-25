from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TASK_STATUS = {"pending", "in_progress", "passed", "failed", "blocked"}
GATE_STATUS = {"pending", "in_progress", "passed", "failed"}
CONTRACT_V2_PREDECESSOR = "d8585c707dcc6413e9fb5bb33212342918837163"
CONTRACT_VERSION_PATH = "CONTRACT_VERSION.json"
EXPECTED_TASKS = ["RS-000", "RS-010", "RS-020", "RS-030", "RS-040", "RS-050", "RS-060", "RS-070", "RS-080"]
EXPECTED_GRAPH_SHA256 = "f94aa906dbedfd64fda5129b0ec34f6f6ebccedd5858dd830df27339ccdff917"
EXPECTED_REGISTRY_SHA256 = "e1d88136123df8f77dc6927485e9dfd4ff9ed4519142065743cbea46b95255ab"
EXPECTED_GATE_ASSERTIONS = {
    "RS-G13": ["clean-install-py311", "clean-install-py312", "clean-install-py313", "wheel-sdist-smoke", "cli-smoke"],
    "RS-G01": ["public-processor-only", "default-exporter-replaced", "no-duplicate-export", "sdk-private-import-scan", "synthetic-trace-captured"],
    "RS-G02": ["files-canary-free", "archives-canary-free", "stdio-canary-free", "exceptions-canary-free", "redaction-before-write"],
    "RS-G03": ["capsule-hash-repeatable", "member-hashes-verified", "traversal-rejected", "archive-bomb-rejected", "malformed-reference-rejected"],
    "RS-G04": ["provider-key-absent", "network-denied", "recorded-values-materialized", "predicate-only-executed", "provider-call-canary-untouched", "original-tool-canary-untouched", "target-failure-reproduced"],
    "RS-G05": ["source-events-247", "reduced-events-max-10", "predicate-preserved", "referential-integrity"],
    "RS-G06": ["every-unit-removal-checked", "no-removable-reproducer", "invalid-reasons-recorded"],
    "RS-G07": ["reproduces-distinct", "absent-distinct", "invalid-distinct", "timeout-invalid", "signal-invalid"],
    "RS-G08": ["span-reduction", "message-reduction", "tool-pair-reduction", "json-field-reduction", "text-reduction", "file-reduction", "environment-reduction"],
    "RS-G09": ["k-of-n-predicate-bookkeeping", "fresh-trial-isolation", "cache-key-complete", "attempt-report-complete", "probabilistic-predicate-label"],
    "RS-G10": ["fresh-temp-run", "linux-one-command", "macos-one-command", "no-source-repository", "no-api-key"],
    "RS-G11": ["timeout-bound", "output-cap", "event-cap", "archive-cap", "recursion-cap", "cancellation"],
    "RS-G12": ["clean-checkout", "full-tests", "killer-reduce", "recorded-values-materialize", "predicate-reproduce", "repro-export", "minimality-verify", "terminal-demo-duration"],
}
EXPECTED_GATES = list(EXPECTED_GATE_ASSERTIONS)
MAX_MANIFEST_BYTES = 1_000_000
MAX_BLOB_BYTES = 50_000_000
MAX_TOTAL_EVIDENCE_BYTES = 100_000_000
SHA256 = re.compile(r"^[a-f0-9]{64}$")
GIT_SHA = re.compile(r"^(?:[a-f0-9]{40}|[a-f0-9]{64})$")
IDENTIFIER = re.compile(r"^[A-Z]{2}-(?:G)?\d{2,3}$")
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
RFC3339_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z$")
CLOCK_SKEW_SECONDS = 5 * 60
MANUAL_KIND_TASKS = {
    "github_authentication": ["RS-080"],
    "repository_ownership": ["RS-080"],
    "registry_authentication": ["RS-080"],
    "registry_2fa": ["RS-080"],
    "legal_identity": ["RS-080"],
    "paid_infrastructure": ["RS-080"],
    "protected_settings": ["RS-080"],
}
CONTROL_PLANE_FILES = [
    ".agent-state.json", "AGENTS.md", "CODEX_START.txt", "CODEX_TASKS.json", CONTRACT_VERSION_PATH, "GATE_REGISTRY.json",
    "docs/AUTONOMOUS_LOOP.md", "docs/CONTROL_PLANE.md", "docs/EVIDENCE_CONTRACT.md",
    "docs/PRODUCT_CONTRACT.md", "docs/PROOF_GATES.md", "docs/RELEASE_STANDARD.md",
    "scripts/bootstrap.py", "scripts/contract.py", "scripts/contract_self_test.py",
    "scripts/next_task.py", "scripts/release_gate.py", "scripts/verify.py",
]


def _object(value: Any) -> bool:
    return isinstance(value, dict)


def _exact_set(actual: Any, expected: Any, label: str) -> None:
    left, right = sorted(actual), sorted(expected)
    if left != right:
        raise ValueError(f"{label} mismatch; expected {right}, got {left}")


def _project_document(document: Any, project: str, label: str) -> None:
    if not _object(document) or document.get("schema_version") != 1 or document.get("project") != project:
        raise ValueError(f"{label}: schema/project mismatch")


def validate_contract_version(document: Any) -> dict[str, Any]:
    if not _object(document):
        raise ValueError("CONTRACT_VERSION.json: expected object")
    _exact_set(
        document.keys(),
        ["contract_version", "predecessor_root", "project", "schema_version"],
        "CONTRACT_VERSION.json keys",
    )
    if (
        document.get("schema_version") != 1
        or document.get("project") != "runsieve"
        or document.get("contract_version") != 2
        or document.get("predecessor_root") != CONTRACT_V2_PREDECESSOR
    ):
        raise ValueError("CONTRACT_VERSION.json: identity mismatch")
    if canonical_json(document) != canonical_json(
        {
            "schema_version": 1,
            "project": "runsieve",
            "contract_version": 2,
            "predecessor_root": CONTRACT_V2_PREDECESSOR,
        }
    ):
        raise ValueError("CONTRACT_VERSION.json: non-canonical identity")
    return document


def load_contract_version(root: Path) -> dict[str, Any]:
    try:
        raw = (root / CONTRACT_VERSION_PATH).read_bytes()
        document = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("missing or invalid CONTRACT_VERSION.json") from exc
    if canonical_json(document) != raw:
        raise ValueError("CONTRACT_VERSION.json must be canonical JSON")
    return validate_contract_version(document)


def parse_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not RFC3339_UTC.fullmatch(value):
        raise ValueError(f"{label}: must be RFC3339 UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label}: invalid calendar timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{label}: must use UTC Z")
    return parsed


def validate_execution_state(state: Any, project: str, *, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    if not _object(state) or state.get("schema_version") != 1 or state.get("project") != project:
        raise ValueError(".agent-state.json: schema/project mismatch")
    started_at = parse_utc(state.get("started_at"), ".agent-state.json.started_at")
    if started_at.timestamp() > current.timestamp() + CLOCK_SKEW_SECONDS:
        raise ValueError(".agent-state.json.started_at is implausibly in the future")
    _exact_set(state.keys(), ["project", "schema_version", "started_at"], ".agent-state.json keys")
    return {**state, "started_at_parsed": started_at}


def load_execution_state(root: Path, project: str) -> dict[str, Any]:
    try:
        state = json.loads((root / ".agent-state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"missing or invalid immutable execution state; run bootstrap from a fresh skeleton: {exc}") from exc
    return validate_execution_state(state, project)


def assert_execution_deadline(*, state: dict[str, Any], deadline_hours: float, label: str, timestamp: datetime | None = None) -> None:
    if not isinstance(deadline_hours, (int, float)) or isinstance(deadline_hours, bool) or deadline_hours <= 0:
        raise ValueError(f"{label}: invalid deadline")
    point = timestamp or datetime.now(timezone.utc)
    deadline = state["started_at_parsed"].timestamp() + deadline_hours * 3600
    if point.timestamp() > deadline:
        raise ValueError(f"{label}: hard deadline hour {deadline_hours} was exceeded")


def validate_evidence_window(
    *,
    bootstrap: datetime,
    proof_started: datetime,
    proof_finished: datetime,
    deadline_hour: float,
    now: datetime,
    label: str,
) -> None:
    if proof_started < bootstrap:
        raise ValueError(f"{label}: proof predates immutable execution start")
    if proof_finished < proof_started:
        raise ValueError(f"{label}: proof finished before it started")
    if proof_finished.timestamp() > now.timestamp() + CLOCK_SKEW_SECONDS:
        raise ValueError(f"{label}: proof timestamp is implausibly in the future")
    if proof_finished.timestamp() > bootstrap.timestamp() + deadline_hour * 3600:
        raise ValueError(f"{label}: proof exceeded owning task deadline hour {deadline_hour}")


def normalized_relative_path(value: Any, label: str = "path") -> str:
    if not isinstance(value, str) or not value or len(value) > 512 or "\x00" in value or "\\" in value or Path(value).is_absolute():
        raise ValueError(f"{label}: must be a non-empty relative POSIX path")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError(f"{label}: non-canonical path")
    return value


def _reference_shape(reference: Any, label: str) -> None:
    if not _object(reference) or not isinstance(reference.get("path"), str) or not SHA256.fullmatch(str(reference.get("sha256", ""))):
        raise ValueError(f"{label}: expected {{path, sha256}}")
    _exact_set(reference.keys(), ["path", "sha256"], f"{label} keys")
    normalized_relative_path(reference["path"], f"{label}.path")


def validate_state_shape(*, project: str, graph: dict[str, Any], progress: dict[str, Any], registry: dict[str, Any], manual: dict[str, Any]) -> dict[str, Any]:
    _project_document(graph, project, "CODEX_TASKS.json")
    _project_document(progress, project, "PROGRESS.json")
    _project_document(registry, project, "GATE_REGISTRY.json")
    _project_document(manual, project, "MANUAL_REQUIRED.json")
    if sha256(canonical_json(graph)) != EXPECTED_GRAPH_SHA256:
        raise ValueError("CODEX_TASKS.json: immutable contract digest mismatch")
    if sha256(canonical_json(registry)) != EXPECTED_REGISTRY_SHA256:
        raise ValueError("GATE_REGISTRY.json: immutable contract digest mismatch")
    _exact_set(progress.keys(), ["gates", "project", "schema_version", "tasks", "updated_at"], "PROGRESS.json keys")
    _exact_set(manual.keys(), ["items", "project", "schema_version"], "MANUAL_REQUIRED.json keys")
    parse_utc(progress.get("updated_at"), "PROGRESS.json.updated_at")

    tasks = graph.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("task graph is empty")
    task_ids = [task.get("id") for task in tasks]
    if any(not isinstance(item, str) or not IDENTIFIER.fullmatch(item) for item in task_ids):
        raise ValueError("invalid task ID")
    if len(set(task_ids)) != len(task_ids):
        raise ValueError("duplicate task ID")
    _exact_set(task_ids, EXPECTED_TASKS, "contract task IDs")
    priorities = [task.get("priority") for task in tasks]
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in priorities) or len(set(priorities)) != len(priorities):
        raise ValueError("task priorities must be unique non-negative integers")
    task_set = set(task_ids)
    task_by_id = {task["id"]: task for task in tasks}
    for task in tasks:
        dependencies = task.get("depends_on")
        if not isinstance(dependencies, list) or task["id"] in dependencies or any(dep not in task_set for dep in dependencies):
            raise ValueError(f"{task['id']}: invalid dependencies")
        deadline = task.get("deadline_hour")
        if not isinstance(deadline, (int, float)) or isinstance(deadline, bool) or deadline <= 0:
            raise ValueError(f"{task['id']}: invalid deadline")
        if not isinstance(task.get("objective"), str) or not task["objective"] or not isinstance(task.get("kill_or_pivot"), str) or not task["kill_or_pivot"]:
            raise ValueError(f"{task['id']}: objective/kill_or_pivot missing")
        if not isinstance(task.get("owns_gates"), list) or not task["owns_gates"]:
            raise ValueError(f"{task['id']}: owns_gates must be non-empty")

    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise ValueError(f"task graph cycle at {task_id}")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in task_by_id[task_id]["depends_on"]:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)
    for task_id in task_ids:
        visit(task_id)

    gates = registry.get("gates")
    if not isinstance(gates, list) or not gates:
        raise ValueError("gate registry is empty")
    gate_ids = [gate.get("id") for gate in gates]
    if any(not isinstance(item, str) or not IDENTIFIER.fullmatch(item) for item in gate_ids):
        raise ValueError("invalid gate ID")
    if len(set(gate_ids)) != len(gate_ids):
        raise ValueError("duplicate gate ID")
    _exact_set(gate_ids, EXPECTED_GATES, "contract gate IDs")
    gate_set = set(gate_ids)
    gate_by_id = {gate["id"]: gate for gate in gates}
    for gate in gates:
        if gate.get("owner_task") not in task_set:
            raise ValueError(f"{gate['id']}: owner task does not exist")
        argv = gate.get("argv")
        expected_argv = ["python", "-m", f"scripts.gates.{gate['id'].replace('-', '_')}"]
        if argv != expected_argv:
            raise ValueError(f"{gate['id']}: verifier argv must be {expected_argv}")
        required_assertions = gate.get("required_assertions")
        if not isinstance(required_assertions, list):
            raise ValueError(f"{gate['id']}: required_assertions missing")
        _exact_set(required_assertions, EXPECTED_GATE_ASSERTIONS[gate["id"]], f"{gate['id']} required assertions")
        if len(set(required_assertions)) != len(required_assertions) or any(not isinstance(item, str) or re.fullmatch(r"[a-z0-9][a-z0-9-]{1,79}", item) is None for item in required_assertions):
            raise ValueError(f"{gate['id']}: required_assertions must be unique kebab-case identifiers")
        timeout = gate.get("timeout_seconds")
        if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0 or timeout > 3600:
            raise ValueError(f"{gate['id']}: invalid verifier timeout")
    owned: list[str] = []
    for task in tasks:
        for gate_id in task["owns_gates"]:
            if gate_id not in gate_set:
                raise ValueError(f"{task['id']}: owns unknown gate {gate_id}")
            if gate_by_id[gate_id]["owner_task"] != task["id"]:
                raise ValueError(f"{task['id']}: gate ownership mismatch for {gate_id}")
            owned.append(gate_id)
    _exact_set(owned, gate_ids, "task-owned gate IDs")
    _exact_set((progress.get("tasks") or {}).keys(), task_ids, "progress task IDs")
    _exact_set((progress.get("gates") or {}).keys(), gate_ids, "progress gate IDs")

    items = manual.get("items")
    if not isinstance(items, list):
        raise ValueError("manual items must be an array")
    blocker_ids: set[str] = set()
    open_blockers: dict[str, dict[str, Any]] = {}
    for item in items:
        blocker_id = item.get("id") if _object(item) else None
        if not isinstance(blocker_id, str) or re.fullmatch(r"HUMAN-[0-9]{3}", blocker_id) is None or blocker_id in blocker_ids:
            raise ValueError("manual blocker IDs must be unique HUMAN-NNN identifiers")
        blocker_ids.add(blocker_id)
        kind = item.get("kind")
        if kind not in MANUAL_KIND_TASKS:
            raise ValueError(f"{blocker_id}: unapproved manual blocker kind")
        if item.get("status") not in {"open", "resolved"}:
            raise ValueError(f"{blocker_id}: invalid manual blocker status")
        if not isinstance(item.get("reason"), str) or len(item["reason"]) < 12 or not isinstance(item.get("why_human_only"), str) or len(item["why_human_only"]) < 12:
            raise ValueError(f"{blocker_id}: missing concrete rationale")
        steps = item.get("exact_steps")
        if not isinstance(steps, list) or not steps or any(not isinstance(step, str) or len(step) < 3 for step in steps):
            raise ValueError(f"{blocker_id}: exact_steps must be a non-empty concrete string array")
        blocks_tasks = item.get("blocks_tasks")
        if not isinstance(blocks_tasks, list) or not blocks_tasks or any(task_id not in MANUAL_KIND_TASKS[kind] for task_id in blocks_tasks):
            raise ValueError(f"{blocker_id}: {kind} may block only {', '.join(MANUAL_KIND_TASKS[kind])}")
        if item.get("blocks_release") is not True:
            raise ValueError(f"{blocker_id}: every approved human-only blocker must block release")
        parse_utc(item.get("detected_at"), f"{blocker_id}.detected_at")
        probe = item.get("probe")
        argv = probe.get("argv") if _object(probe) else None
        if not isinstance(argv, list) or not argv or any(not isinstance(part, str) or not part for part in argv) or not isinstance(probe.get("exit_code"), int) or isinstance(probe.get("exit_code"), bool) or probe["exit_code"] == 0 or not isinstance(probe.get("output_excerpt"), str) or not probe["output_excerpt"] or len(probe["output_excerpt"]) > 2000:
            raise ValueError(f"{blocker_id}: probe must record a failing command and bounded output excerpt")
        _exact_set(probe.keys(), ["argv", "exit_code", "output_excerpt"], f"{blocker_id}.probe keys")
        unblock_check = item.get("unblock_check")
        unblock_argv = unblock_check.get("argv") if _object(unblock_check) else None
        if not isinstance(unblock_argv, list) or not unblock_argv or any(not isinstance(part, str) or not part for part in unblock_argv) or unblock_check.get("expected_exit_code") != 0:
            raise ValueError(f"{blocker_id}: unblock_check must be {{argv, expected_exit_code: 0}}")
        _exact_set(unblock_check.keys(), ["argv", "expected_exit_code"], f"{blocker_id}.unblock_check keys")
        required_keys = ["blocks_release", "blocks_tasks", "detected_at", "exact_steps", "id", "kind", "probe", "reason", "status", "unblock_check", "why_human_only"]
        if item["status"] == "resolved":
            parse_utc(item.get("resolved_at"), f"{blocker_id}.resolved_at")
            if not isinstance(item.get("resolution_evidence"), str) or len(item["resolution_evidence"]) < 3:
                raise ValueError(f"{blocker_id}: resolved item requires resolution_evidence")
            required_keys.extend(["resolved_at", "resolution_evidence"])
        _exact_set(item.keys(), required_keys, f"{blocker_id} keys")
        if item["status"] == "open":
            open_blockers[blocker_id] = item

    active = 0
    progress_tasks = progress["tasks"]
    for task_id, state in progress_tasks.items():
        if not _object(state) or state.get("status") not in TASK_STATUS:
            raise ValueError(f"{task_id}: invalid task status")
        _exact_set(state.keys(), ["blocker_ids", "evidence", "notes", "status"], f"{task_id} state keys")
        evidence, blocker_refs = state.get("evidence"), state.get("blocker_ids", [])
        if not isinstance(evidence, list) or not isinstance(blocker_refs, list):
            raise ValueError(f"{task_id}: invalid task state arrays")
        if not isinstance(state.get("notes"), str) or len(state["notes"]) > 20_000:
            raise ValueError(f"{task_id}: notes must be a bounded string")
        if len(set(blocker_refs)) != len(blocker_refs):
            raise ValueError(f"{task_id}: blocker_ids must be unique")
        evidence_paths: set[str] = set()
        for index, reference in enumerate(evidence):
            _reference_shape(reference, f"{task_id}.evidence[{index}]")
            if reference["path"] in evidence_paths:
                raise ValueError(f"{task_id}: duplicate evidence reference {reference['path']}")
            evidence_paths.add(reference["path"])
        if state["status"] == "in_progress":
            active += 1
        if state["status"] != "pending":
            for dependency in task_by_id[task_id]["depends_on"]:
                if progress_tasks[dependency]["status"] != "passed":
                    raise ValueError(f"{task_id}: {state['status']} while dependency {dependency} is not passed")
        if state["status"] == "blocked":
            if not blocker_refs:
                raise ValueError(f"{task_id}: blocked without blocker_ids")
            for blocker_id in blocker_refs:
                blocker = open_blockers.get(blocker_id)
                if blocker is None or task_id not in blocker["blocks_tasks"]:
                    raise ValueError(f"{task_id}: blocker {blocker_id} is not an open matching manual item")
        elif blocker_refs:
            raise ValueError(f"{task_id}: blocker_ids present while status is {state['status']}")
        owned_gate_states = [progress["gates"][gate_id]["status"] for gate_id in task_by_id[task_id]["owns_gates"]]
        if state["status"] == "passed" and any(status != "passed" for status in owned_gate_states):
            raise ValueError(f"{task_id}: passed before all owned gates passed")
    if active > 1:
        raise ValueError("at most one task may be in_progress")

    for gate_id, state in progress["gates"].items():
        if not _object(state) or state.get("status") not in GATE_STATUS or not isinstance(state.get("evidence"), list):
            raise ValueError(f"{gate_id}: invalid gate state")
        _exact_set(state.keys(), ["evidence", "status"], f"{gate_id} state keys")
        evidence_paths = set()
        for index, reference in enumerate(state["evidence"]):
            _reference_shape(reference, f"{gate_id}.evidence[{index}]")
            if reference["path"] in evidence_paths:
                raise ValueError(f"{gate_id}: duplicate evidence reference {reference['path']}")
            evidence_paths.add(reference["path"])
        if state["status"] == "passed" and not state["evidence"]:
            raise ValueError(f"{gate_id}: passed without evidence")
        owner = gate_by_id[gate_id]["owner_task"]
        if state["status"] == "passed" and progress_tasks[owner]["status"] != "passed":
            raise ValueError(f"{gate_id}: passed while owner task {owner} is not passed")
        if state["status"] == "in_progress" and progress_tasks[owner]["status"] != "in_progress":
            raise ValueError(f"{gate_id}: in_progress while owner task {owner} is not in_progress")
    return {"task_ids": task_ids, "gate_ids": gate_ids, "open_blockers": open_blockers}


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_existing_file(base: Path, relative: str, label: str) -> Path:
    normalized_relative_path(relative, label)
    base_real = base.resolve(strict=True)
    cursor = base_real
    for part in relative.split("/"):
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(f"{label}: symbolic links are forbidden")
        if not cursor.exists():
            raise ValueError(f"{label}: file does not exist")
    target = cursor.resolve(strict=True)
    try:
        target.relative_to(base_real)
    except ValueError as exc:
        raise ValueError(f"{label}: escapes allowed directory") from exc
    if not target.is_file():
        raise ValueError(f"{label}: is not a file")
    return target


def _blob(base: Path, reference: Any, label: str, tracker: dict[str, Any]) -> Path:
    if not _object(reference) or not isinstance(reference.get("path"), str) or not SHA256.fullmatch(str(reference.get("sha256", ""))) or not isinstance(reference.get("bytes"), int) or isinstance(reference.get("bytes"), bool) or reference["bytes"] < 0 or reference["bytes"] > MAX_BLOB_BYTES:
        raise ValueError(f"{label}: expected bounded {{path, sha256, bytes}}")
    _exact_set(reference.keys(), ["bytes", "path", "sha256"], f"{label} keys")
    if reference["path"] in tracker["paths"]:
        raise ValueError(f"{label}: duplicate referenced path {reference['path']}")
    tracker["paths"].add(reference["path"])
    tracker["total_bytes"] += reference["bytes"]
    if tracker["total_bytes"] > MAX_TOTAL_EVIDENCE_BYTES:
        raise ValueError(f"{label}: total evidence exceeds {MAX_TOTAL_EVIDENCE_BYTES} bytes")
    target = _safe_existing_file(base, reference["path"], f"{label}.path")
    data = target.read_bytes()
    if len(data) != reference["bytes"] or sha256(data) != reference["sha256"]:
        raise ValueError(f"{label}: hash/size mismatch")
    return target


def verify_evidence_reference(*, project: str, root: Path, gate: str, gate_spec: dict[str, Any], reference: dict[str, Any]) -> tuple[dict[str, Any], Path]:
    _reference_shape(reference, gate)
    parts = reference["path"].split("/")
    if len(parts) != 4 or parts[0] != ".evidence" or parts[1] != gate or not RUN_ID.fullmatch(parts[2]) or parts[3] != "manifest.json":
        raise ValueError(f"{gate}: manifest path must be .evidence/{gate}/<run-id>/manifest.json")
    manifest_path = _safe_existing_file(root, reference["path"], f"{gate}.manifest")
    if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError(f"{gate}: manifest exceeds {MAX_MANIFEST_BYTES} bytes")
    raw = manifest_path.read_bytes()
    if sha256(raw) != reference["sha256"]:
        raise ValueError(f"{gate}: manifest hash mismatch")
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{gate}: manifest is not valid JSON") from exc
    if canonical_json(manifest) != raw:
        raise ValueError(f"{gate}: manifest is not canonical JSON (sorted one-line JSON plus LF)")
    if not _object(manifest) or manifest.get("schema_version") != 1 or manifest.get("project") != project or manifest.get("gate") != gate or manifest.get("result") != "passed":
        raise ValueError(f"{gate}: invalid manifest identity/result")
    _exact_set(
        manifest.keys(),
        ["artifacts", "assertions", "commands", "commit", "dirty", "environment", "finished_at", "gate", "project", "result", "schema_version", "started_at", "verifier"],
        f"{gate} manifest keys",
    )
    started_at = parse_utc(manifest.get("started_at"), f"{gate}.started_at")
    finished_at = parse_utc(manifest.get("finished_at"), f"{gate}.finished_at")
    if finished_at < started_at:
        raise ValueError(f"{gate}: finished_at precedes started_at")
    if not GIT_SHA.fullmatch(str(manifest.get("commit", ""))) or manifest.get("dirty") is not False:
        raise ValueError(f"{gate}: evidence requires a full Git SHA and dirty=false at proof start")
    environment = manifest.get("environment")
    if not _object(environment) or not environment:
        raise ValueError(f"{gate}: environment is empty")
    assertions = manifest.get("assertions")
    if not isinstance(assertions, list) or not assertions or len(assertions) > 1000:
        raise ValueError(f"{gate}: assertions must contain 1..1000 items")
    seen_assertions: set[str] = set()
    for assertion in assertions:
        assertion_id = assertion.get("id") if _object(assertion) else None
        if not isinstance(assertion_id, str) or not assertion_id or assertion.get("passed") is not True or assertion_id in seen_assertions:
            raise ValueError(f"{gate}: assertion IDs must be unique, explicit, and passed")
        _exact_set(assertion.keys(), ["id", "passed"], f"{gate}.{assertion_id} assertion keys")
        seen_assertions.add(assertion_id)
    for required in gate_spec["required_assertions"]:
        if required not in seen_assertions:
            raise ValueError(f"{gate}: manifest is missing required assertion {required}")
    base = manifest_path.parent
    tracker: dict[str, Any] = {"paths": set(), "total_bytes": 0}
    commands = manifest.get("commands")
    if not isinstance(commands, list) or not commands or len(commands) > 100:
        raise ValueError(f"{gate}: commands must contain 1..100 items")
    for index, command in enumerate(commands):
        argv = command.get("argv") if _object(command) else None
        if not isinstance(argv, list) or not argv or any(not isinstance(part, str) or not part for part in argv) or not isinstance(command.get("exit_code"), int) or isinstance(command.get("exit_code"), bool):
            raise ValueError(f"{gate}: invalid command {index}")
        _exact_set(command.keys(), ["argv", "exit_code", "stderr", "stdout"], f"{gate}.commands[{index}] keys")
        _blob(base, command.get("stdout"), f"{gate}.commands[{index}].stdout", tracker)
        _blob(base, command.get("stderr"), f"{gate}.commands[{index}].stderr", tracker)
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts or len(artifacts) > 200:
        raise ValueError(f"{gate}: artifacts must contain 1..200 items")
    seen_artifacts: set[str] = set()
    for index, artifact in enumerate(artifacts):
        path_value = artifact.get("path") if _object(artifact) else None
        if path_value in seen_artifacts:
            raise ValueError(f"{gate}: duplicate artifact path")
        seen_artifacts.add(path_value)
        _blob(base, artifact, f"{gate}.artifacts[{index}]", tracker)
    verifier = manifest.get("verifier")
    if not _object(verifier) or verifier.get("exit_code") != 0 or verifier.get("argv") != gate_spec["argv"]:
        raise ValueError(f"{gate}: recorded verifier does not match GATE_REGISTRY.json")
    _exact_set(verifier.keys(), ["argv", "bytes", "exit_code", "path", "sha256"], f"{gate}.verifier keys")
    verifier_path_value = gate_spec["argv"][2].replace(".", "/") + ".py"
    if verifier.get("path") != verifier_path_value or SHA256.fullmatch(str(verifier.get("sha256", ""))) is None or not isinstance(verifier.get("bytes"), int) or isinstance(verifier.get("bytes"), bool) or verifier["bytes"] < 1 or verifier["bytes"] > MAX_BLOB_BYTES:
        raise ValueError(f"{gate}: verifier identity/hash is missing or invalid")
    verifier_path = _safe_existing_file(root, verifier_path_value, f"{gate}.verifier.path")
    verifier_bytes = verifier_path.read_bytes()
    if len(verifier_bytes) != verifier["bytes"] or sha256(verifier_bytes) != verifier["sha256"]:
        raise ValueError(f"{gate}: verifier implementation differs from the proved version")
    committed = subprocess.run(
        ["git", "show", f"{manifest['commit']}:{verifier_path_value}"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if committed.returncode:
        raise ValueError(f"{gate}: verifier implementation is absent from evidence commit {manifest['commit']}")
    if len(committed.stdout) != verifier["bytes"] or sha256(committed.stdout) != verifier["sha256"]:
        raise ValueError(f"{gate}: verifier hash is not tied to the recorded clean evidence commit")
    return manifest, manifest_path


def assert_evidence_files_tracked(*, root: Path, gate: str, manifest_path: Path, manifest: dict[str, Any]) -> None:
    root_real = root.resolve(strict=True)
    base = manifest_path.parent
    targets = [manifest_path.resolve(strict=True)]
    for index, command in enumerate(manifest["commands"]):
        targets.append(_safe_existing_file(base, command["stdout"]["path"], f"{gate}.commands[{index}].stdout.path"))
        targets.append(_safe_existing_file(base, command["stderr"]["path"], f"{gate}.commands[{index}].stderr.path"))
    for index, artifact in enumerate(manifest["artifacts"]):
        targets.append(_safe_existing_file(base, artifact["path"], f"{gate}.artifacts[{index}].path"))
    targets.append(_safe_existing_file(root_real, manifest["verifier"]["path"], f"{gate}.verifier.path"))

    for target in dict.fromkeys(targets):
        try:
            relative = target.relative_to(root_real).as_posix()
        except ValueError as exc:
            raise ValueError(f"{gate}: evidence file escapes repository: {target}") from exc
        tracked = _git(root_real, "ls-files", "--error-unmatch", "--", relative)
        committed = _git(root_real, "cat-file", "-e", f"HEAD:{relative}")
        if tracked.returncode or committed.returncode:
            raise ValueError(f"{gate}: evidence file is not Git-tracked in HEAD: {relative}")


def run_resolved_unblock_check(*, root: Path, item: dict[str, Any]) -> None:
    if item["status"] != "resolved":
        return
    check = item["unblock_check"]
    try:
        result = subprocess.run(
            check["argv"],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"{item['id']}: unblock_check failed to run: {exc}") from exc
    if result.returncode != check["expected_exit_code"]:
        excerpt = (result.stderr + result.stdout).strip()[:1000]
        raise ValueError(f"{item['id']}: resolved blocker did not pass unblock_check (exit {result.returncode}); {excerpt}")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)


def control_plane_bundle_identity(root: Path, revision: str | None = None) -> dict[str, Any]:
    version = load_contract_version(root) if revision is None else None
    files: list[dict[str, Any]] = []
    aggregate = hashlib.sha256()
    for path in sorted(CONTROL_PLANE_FILES):
        if revision is None:
            try:
                data = (root / path).read_bytes()
            except OSError as exc:
                raise ValueError(f"control-plane file is missing: {path}") from exc
        else:
            completed = subprocess.run(
                ["git", "show", f"{revision}:{path}"],
                cwd=root,
                capture_output=True,
                check=False,
            )
            if completed.returncode:
                raise ValueError(f"{revision}: missing control-plane file {path}")
            data = completed.stdout
        aggregate.update(path.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(data)
        aggregate.update(b"\0")
        files.append({"path": path, "bytes": len(data), "sha256": sha256(data)})
        if path == CONTRACT_VERSION_PATH and revision is not None:
            try:
                version = validate_contract_version(json.loads(data))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"{revision}: invalid CONTRACT_VERSION.json") from exc
            if canonical_json(version) != data:
                raise ValueError(f"{revision}: CONTRACT_VERSION.json is not canonical JSON")
    if version is None:
        raise ValueError("control-plane bundle has no contract identity")
    return {
        "aggregate_algorithm": "sha256(sorted(path + NUL + bytes + NUL))",
        "aggregate_sha256": aggregate.hexdigest(),
        "contract_version": version["contract_version"],
        "files": files,
        "predecessor_root": version["predecessor_root"],
        "project": version["project"],
        "schema_version": 1,
    }


def assert_clean_git(root: Path) -> None:
    inside = _git(root, "rev-parse", "--is-inside-work-tree")
    if inside.returncode or inside.stdout.strip() != "true":
        raise ValueError("release gate requires a Git repository; run python -m scripts.bootstrap")
    top = _git(root, "rev-parse", "--show-toplevel")
    if top.returncode or Path(top.stdout.strip()).resolve() != root.resolve():
        raise ValueError("project directory must be the Git repository root")
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if status.returncode or status.stdout.strip():
        raise ValueError("working tree contains tracked or untracked changes; commit coherent work before release verification")


def assert_control_plane_unchanged(root: Path) -> None:
    load_contract_version(root)
    roots = _git(root, "rev-list", "--max-parents=0", "HEAD")
    commits = roots.stdout.strip().splitlines() if roots.returncode == 0 else []
    if len(commits) != 1 or GIT_SHA.fullmatch(commits[0]) is None:
        raise ValueError("control plane requires exactly one Git root commit")
    for path in CONTROL_PLANE_FILES:
        anchored = _git(root, "cat-file", "-e", f"{commits[0]}:{path}")
        if anchored.returncode:
            raise ValueError(f"bootstrap root commit is missing control-plane file {path}")
    diff = _git(root, "diff", "--quiet", commits[0], "--", *CONTROL_PLANE_FILES)
    if diff.returncode:
        raise ValueError("immutable control-plane files differ from the bootstrap root commit; restore them instead of weakening the contract")
    anchored_bundle = control_plane_bundle_identity(root, commits[0])
    current_bundle = control_plane_bundle_identity(root)
    if anchored_bundle != current_bundle:
        raise ValueError("current control-plane bundle identity differs from the bootstrap root")


def assert_commit_exists(root: Path, commit: str, label: str) -> None:
    result = _git(root, "cat-file", "-e", f"{commit}^{{commit}}")
    if result.returncode:
        raise ValueError(f"{label}: evidence commit does not exist in this repository")
    ancestor = _git(root, "merge-base", "--is-ancestor", commit, "HEAD")
    if ancestor.returncode:
        raise ValueError(f"{label}: evidence commit is not an ancestor of HEAD")


def run_gate_verifier(*, root: Path, gate_spec: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    argv = list(gate_spec["argv"])
    if argv[0] in {"python", "python3"}:
        argv[0] = sys.executable
    try:
        result = subprocess.run(
            [*argv, str(manifest_path)], cwd=root, text=True, capture_output=True,
            timeout=gate_spec["timeout_seconds"], check=False,
            env={**os.environ, "RUNSIEVE_RELEASE_VERIFY": "1"},
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"{gate_spec['id']}: verifier timed out") from exc
    if result.returncode:
        raise ValueError(f"{gate_spec['id']}: verifier exit {result.returncode}; {result.stderr.strip()}")
    try:
        report = json.loads(result.stdout.strip())
    except json.JSONDecodeError as exc:
        raise ValueError(f"{gate_spec['id']}: verifier stdout must be exactly one JSON object") from exc
    assertions = report.get("assertions") if _object(report) else None
    if not _object(report) or report.get("gate") != gate_spec["id"] or report.get("passed") is not True or not isinstance(assertions, list) or not assertions or len(assertions) > 1000 or any(not _object(item) or not isinstance(item.get("id"), str) or not item["id"] or item.get("passed") is not True for item in assertions):
        raise ValueError(f"{gate_spec['id']}: verifier report is invalid or contains failed assertions")
    _exact_set(report.keys(), ["assertions", "gate", "passed"], f"{gate_spec['id']} verifier report keys")
    for item in assertions:
        _exact_set(item.keys(), ["id", "passed"], f"{gate_spec['id']}.{item['id']} verifier assertion keys")
    assertion_ids = [item["id"] for item in assertions]
    if len(set(assertion_ids)) != len(assertion_ids):
        raise ValueError(f"{gate_spec['id']}: verifier assertion IDs must be unique")
    for required in gate_spec["required_assertions"]:
        if required not in assertion_ids:
            raise ValueError(f"{gate_spec['id']}: verifier report is missing required assertion {required}")
    return report


def load_project_documents(root: Path, project: str) -> dict[str, Any]:
    def load(name: str) -> dict[str, Any]:
        return json.loads((root / name).read_text(encoding="utf-8"))
    contract_version = load_contract_version(root)
    documents = {"project": project, "graph": load("CODEX_TASKS.json"), "progress": load("PROGRESS.json"), "registry": load("GATE_REGISTRY.json"), "manual": load("MANUAL_REQUIRED.json")}
    shape = validate_state_shape(**documents)
    return {**documents, **shape, "contract_version": contract_version}
