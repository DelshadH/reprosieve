from __future__ import annotations

import importlib
import json
import os
import platform
import shutil
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
from scripts.gates._verify import GateSpec

ROOT = Path(__file__).resolve().parents[1]


def build_manifest(
    *,
    gate: str,
    commit: str,
    started_at: str,
    finished_at: str,
    environment: dict[str, str],
    assertions: tuple[str, ...],
    command: dict[str, object] | None = None,
    commands: tuple[dict[str, object], ...] = (),
    artifacts: tuple[dict[str, object], ...],
    verifier: dict[str, object],
) -> dict[str, object]:
    if (command is None) == (not commands):
        raise ValueError("provide exactly one command or a non-empty commands tuple")
    selected_commands = commands if commands else (command,)
    return {
        "artifacts": list(artifacts),
        "assertions": [{"id": assertion, "passed": True} for assertion in assertions],
        "commands": list(selected_commands),
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


def build_measurement_proof(
    spec: GateSpec,
    *,
    commit: str,
    commands: tuple[dict[str, object], ...],
) -> dict[str, object]:
    if len(commands) != len(spec.measurements):
        raise ValueError("gate proof command count differs from its measurements")
    records: list[dict[str, object]] = []
    for measurement, command in zip(spec.measurements, commands, strict=True):
        stdout = command.get("stdout")
        stderr = command.get("stderr")
        if (
            command.get("argv") != list(measurement.argv)
            or command.get("exit_code") != 0
            or not isinstance(stdout, dict)
            or not isinstance(stderr, dict)
            or not isinstance(stdout.get("sha256"), str)
            or not isinstance(stderr.get("sha256"), str)
        ):
            raise ValueError("gate proof command does not match its measurement")
        records.append(
            {
                "argv": list(measurement.argv),
                "assertions": list(measurement.assertions),
                "exit_code": 0,
                "kind": measurement.kind,
                "platform": measurement.platform,
                "stderr_sha256": stderr["sha256"],
                "stdout_sha256": stdout["sha256"],
            }
        )
    return {
        "commit": commit,
        "gate": spec.gate,
        "measurements": records,
        "schema_version": 1,
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


def _gate_registry_spec(gate: str) -> dict[str, Any]:
    documents = load_project_documents(ROOT, "runsieve")
    for spec in documents["registry"]["gates"]:
        if spec["id"] == gate:
            return spec
    raise ValueError(f"unknown gate: {gate}")


def _measurement_spec(gate: str) -> GateSpec:
    module = importlib.import_module(f"scripts.gates.{gate.replace('-', '_')}")
    spec = getattr(module, "SPEC", None)
    if not isinstance(spec, GateSpec) or spec.gate != gate:
        raise RuntimeError(f"{gate} does not expose a gate-specific measurement spec")
    return spec


def _execute_measurements(
    spec: GateSpec,
    *,
    directory: Path,
    timeout_seconds: int,
) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
    commands: list[dict[str, object]] = []
    for index, measurement in enumerate(spec.measurements):
        if measurement.kind != "pytest":
            raise RuntimeError(
                f"{spec.gate} requires externally produced portable proof inputs"
            )
        executed_argv = [
            sys.executable if position == 0 and part == "python" else part
            for position, part in enumerate(measurement.argv)
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
            timeout=timeout_seconds,
            check=False,
        )
        stdout_path = directory / f"command-{index:02d}.stdout"
        stderr_path = directory / f"command-{index:02d}.stderr"
        stdout_path.write_bytes(completed.stdout)
        stderr_path.write_bytes(completed.stderr)
        if completed.returncode:
            raise RuntimeError(
                f"{spec.gate} measurement {index} failed with exit "
                f"{completed.returncode}; see {stderr_path.relative_to(ROOT)}"
            )
        commands.append(
            {
                "argv": list(measurement.argv),
                "exit_code": completed.returncode,
                "stderr": blob_reference(stderr_path, relative_to=directory),
                "stdout": blob_reference(stdout_path, relative_to=directory),
            }
        )
    return tuple(commands), ()


def _portable_inputs(
    spec: GateSpec,
    *,
    commit: str,
    directory: Path,
    proof_inputs: tuple[Path, ...],
) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
    from scripts.gates.RS_G10 import validate_portable_proof

    if len(proof_inputs) != 2:
        raise RuntimeError("RS-G10 requires one Linux and one macOS proof directory")
    by_platform: dict[str, tuple[Path, dict[str, Any]]] = {}
    for input_directory in proof_inputs:
        if input_directory.is_symlink() or not input_directory.is_dir():
            raise RuntimeError("portable proof input must be a regular directory")
        source_proof = input_directory / "proof.json"
        if source_proof.is_symlink() or not source_proof.is_file():
            raise RuntimeError("portable proof input is missing proof.json")
        try:
            proof = json.loads(source_proof.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("portable proof input contains invalid JSON") from error
        runner = proof.get("runner") if isinstance(proof, dict) else None
        selected_platform = runner.get("os") if isinstance(runner, dict) else None
        if selected_platform not in {"linux", "macos"} or selected_platform in by_platform:
            raise RuntimeError("portable proof inputs must contain distinct Linux and macOS runs")
        validate_portable_proof(
            proof,
            expected_os=selected_platform,
            expected_commit=commit,
        )
        by_platform[selected_platform] = (input_directory, proof)

    commands: list[dict[str, object]] = []
    artifacts: list[dict[str, object]] = []
    for measurement in spec.measurements:
        selected_platform = measurement.platform
        if selected_platform is None or selected_platform not in by_platform:
            raise RuntimeError("portable proof platform does not match the gate spec")
        source_directory, proof = by_platform[selected_platform]
        destination = directory / f"portable-{selected_platform}"
        destination.mkdir()
        for name in (
            "proof.json",
            "command.stdout",
            "command.stderr",
            "capsule.runsieve",
            "reproduce.py",
        ):
            source = source_directory / name
            if source.is_symlink() or not source.is_file():
                raise RuntimeError(f"portable proof input is missing regular file {name}")
            target = destination / name
            shutil.copyfile(source, target)
            if name not in {"command.stdout", "command.stderr"}:
                artifacts.append(blob_reference(target, relative_to=directory))
        commands.append(
            {
                "argv": list(measurement.argv),
                "exit_code": proof["command"]["exit_code"],
                "stderr": blob_reference(
                    destination / "command.stderr",
                    relative_to=directory,
                ),
                "stdout": blob_reference(
                    destination / "command.stdout",
                    relative_to=directory,
                ),
            }
        )
    return tuple(commands), tuple(artifacts)


def generate(
    gate: str,
    *,
    run_id: str | None = None,
    proof_inputs: tuple[Path, ...] = (),
) -> dict[str, str]:
    commit = _clean_commit()
    registry_spec = _gate_registry_spec(gate)
    measurement_spec = _measurement_spec(gate)
    if set(measurement_spec.assertions) != set(registry_spec["required_assertions"]):
        raise RuntimeError(f"{gate} measurement assertions differ from the registry")
    selected_run_id = run_id or (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{commit[:12]}"
    )
    directory = ROOT / ".evidence" / gate / selected_run_id
    if directory.exists() or directory.is_symlink():
        raise FileExistsError("evidence run directory already exists")
    directory.mkdir(parents=True)
    manifest_path = directory / "manifest.json"
    started_at = _utc_now()

    if gate == "RS-G10":
        commands, external_artifacts = _portable_inputs(
            measurement_spec,
            commit=commit,
            directory=directory,
            proof_inputs=proof_inputs,
        )
    else:
        if proof_inputs:
            raise ValueError("proof inputs are supported only for RS-G10")
        commands, external_artifacts = _execute_measurements(
            measurement_spec,
            directory=directory,
            timeout_seconds=registry_spec["timeout_seconds"],
        )
    proof_path = directory / "proof.json"
    write_canonical_json(
        proof_path,
        build_measurement_proof(
            measurement_spec,
            commit=commit,
            commands=commands,
        ),
    )
    verifier_path_value = registry_spec["argv"][2].replace(".", "/") + ".py"
    verifier_path = ROOT / verifier_path_value
    verifier_bytes = verifier_path.read_bytes()
    verifier = {
        "argv": registry_spec["argv"],
        "bytes": len(verifier_bytes),
        "exit_code": 0,
        "path": verifier_path_value,
        "sha256": sha256(verifier_bytes),
    }
    manifest = build_manifest(
        gate=gate,
        commit=commit,
        started_at=started_at,
        finished_at=_utc_now(),
        environment={
            "os": platform.system().lower(),
            "python": platform.python_version(),
        },
        assertions=measurement_spec.assertions,
        commands=commands,
        artifacts=(
            blob_reference(proof_path, relative_to=directory),
            *external_artifacts,
        ),
        verifier=verifier,
    )
    write_canonical_json(manifest_path, manifest)
    reference = {
        "path": manifest_path.relative_to(ROOT).as_posix(),
        "sha256": sha256(manifest_path.read_bytes()),
    }
    verify_evidence_reference(
        project="runsieve",
        root=ROOT,
        gate=gate,
        gate_spec=registry_spec,
        reference=reference,
    )
    run_gate_verifier(
        root=ROOT,
        gate_spec=registry_spec,
        manifest_path=manifest_path,
    )
    return reference


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    proof_inputs: list[Path] = []
    positionals: list[str] = []
    index = 0
    while index < len(arguments):
        if arguments[index] == "--proof-input":
            if index + 1 >= len(arguments):
                print("evidence generation failed: --proof-input needs a path", file=sys.stderr)
                return 2
            proof_inputs.append(Path(arguments[index + 1]))
            index += 2
        else:
            positionals.append(arguments[index])
            index += 1
    if len(positionals) not in {1, 2}:
        print(
            "usage: python -m scripts.generate_gate_evidence "
            "RS-Gxx [run-id] [--proof-input DIR ...]",
            file=sys.stderr,
        )
        return 2
    try:
        reference = generate(
            positionals[0],
            run_id=positionals[1] if len(positionals) == 2 else None,
            proof_inputs=tuple(proof_inputs),
        )
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        print(f"evidence generation failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(reference, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
