from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.contract import (
    load_project_documents,
    run_gate_verifier,
    sha256,
    verify_evidence_reference,
)
from scripts.evidence import blob_reference, write_canonical_json

ROOT = Path(__file__).resolve().parents[1]


def build_manifest(
    *,
    gate: str,
    commit: str,
    started_at: str,
    finished_at: str,
    environment: dict[str, str],
    assertions: tuple[str, ...],
    command: dict[str, object],
    artifacts: tuple[dict[str, object], ...],
    verifier: dict[str, object],
) -> dict[str, object]:
    return {
        "artifacts": list(artifacts),
        "assertions": [{"id": assertion, "passed": True} for assertion in assertions],
        "commands": [command],
        "commit": commit,
        "dirty": False,
        "environment": environment,
        "finished_at": finished_at,
        "gate": gate,
        "project": "runsieve",
        "result": "passed",
        "schema_version": 1,
        "started_at": started_at,
        "verifier": verifier,
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _clean_commit() -> str:
    status = _git("status", "--porcelain=v1", "--untracked-files=all")
    if status.returncode or status.stdout.strip():
        raise RuntimeError("evidence generation requires a clean committed tree")
    commit = _git("rev-parse", "HEAD")
    if commit.returncode or len(commit.stdout.strip()) != 40:
        raise RuntimeError("evidence generation could not resolve HEAD")
    return commit.stdout.strip()


def _gate_spec(gate: str) -> dict[str, Any]:
    documents = load_project_documents(ROOT, "runsieve")
    for spec in documents["registry"]["gates"]:
        if spec["id"] == gate:
            return spec
    raise ValueError(f"unknown gate: {gate}")


def generate(gate: str, *, run_id: str | None = None) -> dict[str, str]:
    commit = _clean_commit()
    spec = _gate_spec(gate)
    selected_run_id = run_id or (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{commit[:12]}"
    )
    directory = ROOT / ".evidence" / gate / selected_run_id
    if directory.exists() or directory.is_symlink():
        raise FileExistsError("evidence run directory already exists")
    directory.mkdir(parents=True)
    manifest_path = directory / "manifest.json"
    write_canonical_json(manifest_path, {"gate": gate})

    started_at = _utc_now()
    relative_manifest = manifest_path.relative_to(ROOT).as_posix()
    recorded_argv = [*spec["argv"], relative_manifest]
    executed_argv = [
        sys.executable if part in {"python", "python3"} and index == 0 else part
        for index, part in enumerate(recorded_argv)
    ]
    completed = subprocess.run(
        executed_argv,
        cwd=ROOT,
        env={
            **os.environ,
            "PYTHONPATH": str(ROOT / "src")
            + os.pathsep
            + os.environ.get("PYTHONPATH", ""),
        },
        capture_output=True,
        text=False,
        timeout=spec["timeout_seconds"],
        check=False,
    )
    stdout_path = directory / "command.stdout"
    stderr_path = directory / "command.stderr"
    stdout_path.write_bytes(completed.stdout)
    stderr_path.write_bytes(completed.stderr)
    if completed.returncode:
        raise RuntimeError(
            f"{gate} proof command failed with exit {completed.returncode}; "
            f"see {stderr_path.relative_to(ROOT)}"
        )
    try:
        report = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"{gate} verifier emitted an invalid report") from error
    if not isinstance(report, dict) or report.get("gate") != gate or report.get("passed") is not True:
        raise RuntimeError(f"{gate} verifier did not pass")
    report_assertions = report.get("assertions")
    if not isinstance(report_assertions, list):
        raise RuntimeError(f"{gate} verifier report has no assertions")
    assertion_ids = tuple(
        item["id"]
        for item in report_assertions
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    )
    if set(assertion_ids) != set(spec["required_assertions"]):
        raise RuntimeError(f"{gate} verifier assertion set differs from the registry")

    proof_path = directory / "proof.json"
    write_canonical_json(
        proof_path,
        {
            "assertions": list(assertion_ids),
            "commit": commit,
            "gate": gate,
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
    )
    verifier_path_value = spec["argv"][2].replace(".", "/") + ".py"
    verifier_path = ROOT / verifier_path_value
    verifier_bytes = verifier_path.read_bytes()
    verifier = {
        "argv": spec["argv"],
        "bytes": len(verifier_bytes),
        "exit_code": 0,
        "path": verifier_path_value,
        "sha256": sha256(verifier_bytes),
    }
    command = {
        "argv": recorded_argv,
        "exit_code": completed.returncode,
        "stderr": blob_reference(stderr_path, relative_to=directory),
        "stdout": blob_reference(stdout_path, relative_to=directory),
    }
    manifest = build_manifest(
        gate=gate,
        commit=commit,
        started_at=started_at,
        finished_at=_utc_now(),
        environment={"os": platform.system().lower(), "python": platform.python_version()},
        assertions=assertion_ids,
        command=command,
        artifacts=(blob_reference(proof_path, relative_to=directory),),
        verifier=verifier,
    )
    write_canonical_json(manifest_path, manifest)
    reference = {
        "path": relative_manifest,
        "sha256": sha256(manifest_path.read_bytes()),
    }
    verify_evidence_reference(
        project="runsieve",
        root=ROOT,
        gate=gate,
        gate_spec=spec,
        reference=reference,
    )
    run_gate_verifier(root=ROOT, gate_spec=spec, manifest_path=manifest_path)
    return reference


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) not in {1, 2}:
        print("usage: python -m scripts.generate_gate_evidence RS-Gxx [run-id]", file=sys.stderr)
        return 2
    try:
        reference = generate(
            arguments[0],
            run_id=arguments[1] if len(arguments) == 2 else None,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        print(f"evidence generation failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(reference, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
