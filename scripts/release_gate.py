from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from scripts.contract import (
    assert_clean_git,
    assert_commit_exists,
    assert_control_plane_unchanged,
    assert_evidence_files_tracked,
    assert_execution_deadline,
    load_execution_state,
    load_project_documents,
    parse_utc,
    run_gate_verifier,
    run_resolved_unblock_check,
    validate_evidence_window,
    verify_evidence_reference,
)

ROOT = Path(__file__).resolve().parents[1]

def main() -> int:
    failures: list[str] = []
    try:
        docs = load_project_documents(ROOT, "runsieve")
        execution = load_execution_state(ROOT, "runsieve")
        assert_clean_git(ROOT)
        assert_control_plane_unchanged(ROOT)
        assert_execution_deadline(state=execution, deadline_hours=docs["graph"]["deadline_hours_total"], label="RunSieve release")
        progress_updated_at = parse_utc(docs["progress"]["updated_at"], "PROGRESS.json.updated_at")
        now = datetime.now(timezone.utc)
        latest_proof_finished_at = execution["started_at_parsed"]
        if progress_updated_at < execution["started_at_parsed"] or progress_updated_at.timestamp() > now.timestamp() + 5 * 60:
            failures.append("PROGRESS.json.updated_at must fall inside the immutable execution window")
        for item in docs["manual"]["items"]:
            if item["status"] == "open" and item["blocks_release"]:
                failures.append(f"{item['id']}: open human-only release blocker")
            if item["status"] == "resolved":
                try:
                    run_resolved_unblock_check(root=ROOT, item=item)
                except (OSError, TypeError, ValueError) as exc:
                    failures.append(str(exc))
        for task in docs["graph"]["tasks"]:
            status = docs["progress"]["tasks"][task["id"]]["status"]
            if status != "passed":
                failures.append(f"{task['id']}: task is {status}")
        for gate_spec in docs["registry"]["gates"]:
            gate = gate_spec["id"]
            state = docs["progress"]["gates"][gate]
            if state["status"] != "passed":
                failures.append(f"{gate}: gate is {state['status']}")
                continue
            if not state["evidence"]:
                failures.append(f"{gate}: passed without evidence")
                continue
            for reference in state["evidence"]:
                try:
                    manifest, manifest_path = verify_evidence_reference(project="runsieve", root=ROOT, gate=gate, gate_spec=gate_spec, reference=reference)
                    assert_evidence_files_tracked(root=ROOT, gate=gate, manifest_path=manifest_path, manifest=manifest)
                    assert_commit_exists(ROOT, manifest["commit"], gate)
                    owner = next(task for task in docs["graph"]["tasks"] if task["id"] == gate_spec["owner_task"])
                    proof_started_at = parse_utc(manifest["started_at"], f"{gate}.started_at")
                    proof_finished_at = parse_utc(manifest["finished_at"], f"{gate}.finished_at")
                    validate_evidence_window(
                        bootstrap=execution["started_at_parsed"],
                        proof_started=proof_started_at,
                        proof_finished=proof_finished_at,
                        deadline_hour=owner["deadline_hour"],
                        now=now,
                        label=gate,
                    )
                    latest_proof_finished_at = max(latest_proof_finished_at, proof_finished_at)
                    run_gate_verifier(root=ROOT, gate_spec=gate_spec, manifest_path=manifest_path)
                except (OSError, TypeError, ValueError) as exc:
                    failures.append(str(exc) if str(exc).startswith(gate) else f"{gate}: {exc}")
        if progress_updated_at < latest_proof_finished_at:
            failures.append("PROGRESS.json.updated_at predates the latest accepted proof")
        try:
            assert_clean_git(ROOT)
        except (OSError, TypeError, ValueError) as exc:
            failures.append(str(exc))
    except (OSError, KeyError, TypeError, ValueError) as exc:
        failures.append(str(exc))
    if failures:
        print("RunSieve release gate is RED:\n- " + "\n- ".join(failures))
        return 1
    print("RunSieve release gate is GREEN: exact state, clean Git, hashed evidence, and every independent gate verifier passed.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
