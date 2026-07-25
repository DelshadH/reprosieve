from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from scripts.contract import assert_execution_deadline, load_execution_state, load_project_documents

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    docs = load_project_documents(ROOT, "runsieve")
    try:
        state = load_execution_state(ROOT, "runsieve")
    except ValueError as exc:
        print(exc)
        return 2
    elapsed = (datetime.now(timezone.utc) - state["started_at_parsed"]).total_seconds() / 3600
    progress = docs["progress"]["tasks"]
    passed = {task_id for task_id, value in progress.items() if value["status"] == "passed"}
    candidates = [
        task for task in docs["graph"]["tasks"]
        if progress[task["id"]]["status"] in {"pending", "in_progress", "failed"}
        and all(dependency in passed for dependency in task["depends_on"])
    ]
    candidates.sort(key=lambda task: (0 if progress[task["id"]]["status"] == "in_progress" else 1, task["priority"], task["deadline_hour"]))
    if not candidates:
        blocked = [task for task in docs["graph"]["tasks"] if progress[task["id"]]["status"] == "blocked"]
        if blocked:
            details = " ".join(f"{task['id']}[{','.join(progress[task['id']]['blocker_ids'])}]" for task in blocked)
            print(f"No executable task. Human-only blockers: {details}")
        else:
            print("No executable task remains. Run python -m scripts.release_gate.")
        return 0
    task = candidates[0]
    try:
        assert_execution_deadline(state=state, deadline_hours=task["deadline_hour"], label=task["id"])
        overdue = False
    except ValueError:
        overdue = True
    print(f"{task['id']}	{'OVERDUE' if overdue else 'deadline'} hour {task['deadline_hour']}	elapsed {elapsed:.2f}h	{task['objective']}")
    if overdue:
        print(f"KILL/PIVOT NOW: {task['kill_or_pivot']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
