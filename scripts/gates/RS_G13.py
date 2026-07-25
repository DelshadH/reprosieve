from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from scripts.gates._verify import GateSpec, Measurement, verify_gate

ROOT = Path(__file__).resolve().parents[2]
SHA256 = re.compile(r"^[a-f0-9]{64}$")
PYTHON_MINORS = ("3.11", "3.12", "3.13")
MAX_PROOF_BLOB = 50_000_000


def _output_reference(value: object, *, label: str) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != {"bytes", "sha256"}
        or isinstance(value.get("bytes"), bool)
        or not isinstance(value.get("bytes"), int)
        or not 0 <= value["bytes"] <= MAX_PROOF_BLOB
        or not isinstance(value.get("sha256"), str)
        or SHA256.fullmatch(value["sha256"]) is None
    ):
        raise ValueError(f"{label} is not a bounded output reference")


def _artifact_reference(value: object, *, suffix: str, label: str) -> None:
    if not isinstance(value, dict) or set(value) != {"bytes", "name", "sha256"}:
        raise ValueError(f"{label} is not a complete artifact reference")
    name = value.get("name")
    if (
        not isinstance(name, str)
        or Path(name).name != name
        or not name.endswith(suffix)
        or isinstance(value.get("bytes"), bool)
        or not isinstance(value.get("bytes"), int)
        or not 1 <= value["bytes"] <= MAX_PROOF_BLOB
        or not isinstance(value.get("sha256"), str)
        or SHA256.fullmatch(value["sha256"]) is None
    ):
        raise ValueError(f"{label} is invalid")


def validate_package_proof(
    proof: object,
    *,
    expected_python: str,
    expected_commit: str,
    expected_os: str = "linux",
) -> set[str]:
    if expected_python not in PYTHON_MINORS or not isinstance(proof, dict):
        raise ValueError("RS-G13 package proof identity is invalid")
    if set(proof) != {
        "artifacts",
        "clean_install_directory",
        "collector",
        "commands",
        "commit",
        "fresh_checkout",
        "gate",
        "runner",
        "schema_version",
        "source_tree_present",
    }:
        raise ValueError("RS-G13 package proof fields are incomplete")
    collector = proof.get("collector")
    runner = proof.get("runner")
    artifacts = proof.get("artifacts")
    commands = proof.get("commands")
    if (
        proof.get("schema_version") != 1
        or proof.get("gate") != "RS-G13"
        or proof.get("commit") != expected_commit
        or proof.get("fresh_checkout") is not True
        or proof.get("clean_install_directory") is not True
        or proof.get("source_tree_present") is not False
        or not isinstance(collector, dict)
        or collector.get("path") != "scripts/package_matrix_proof.py"
        or not isinstance(collector.get("sha256"), str)
        or SHA256.fullmatch(collector["sha256"]) is None
        or not isinstance(runner, dict)
        or set(runner) != {"arch", "os", "python"}
        or runner.get("os") != expected_os
        or not isinstance(runner.get("arch"), str)
        or not runner["arch"]
        or not isinstance(runner.get("python"), str)
        or not runner["python"].startswith(expected_python + ".")
        or not isinstance(artifacts, dict)
        or set(artifacts) != {"sdist", "wheel"}
        or not isinstance(commands, list)
        or len(commands) != 4
    ):
        raise ValueError("RS-G13 package proof did not use a clean supported runner")
    _artifact_reference(
        artifacts["wheel"],
        suffix=".whl",
        label="RS-G13 wheel",
    )
    _artifact_reference(
        artifacts["sdist"],
        suffix=".tar.gz",
        label="RS-G13 sdist",
    )
    wheel_name = artifacts["wheel"]["name"]
    expected_argv = (
        ["python", "-m", "build"],
        ["python", "-m", "venv", "venv"],
        ["python", "-m", "pip", "install", "--no-deps", wheel_name],
        ["runsieve", "--help"],
    )
    for index, (command, argv) in enumerate(zip(commands, expected_argv, strict=True)):
        if (
            not isinstance(command, dict)
            or set(command) != {"argv", "exit_code", "stderr", "stdout"}
            or command.get("argv") != argv
            or command.get("exit_code") != 0
        ):
            raise ValueError(f"RS-G13 package command {index} did not pass")
        _output_reference(command.get("stdout"), label=f"RS-G13 command {index} stdout")
        _output_reference(command.get("stderr"), label=f"RS-G13 command {index} stderr")
    if commands[3]["stdout"]["bytes"] < 1:
        raise ValueError("RS-G13 CLI smoke output is empty")
    suffix = expected_python.replace(".", "")
    assertions = {f"clean-install-py{suffix}"}
    if expected_python == "3.11":
        assertions.update({"wheel-sdist-smoke", "cli-smoke"})
    return assertions


def _read_and_match(path: Path, reference: dict[str, Any], *, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is missing")
    data = path.read_bytes()
    if len(data) != reference["bytes"] or hashlib.sha256(data).hexdigest() != reference["sha256"]:
        raise ValueError(f"{label} hash or size mismatch")
    return data


def _validate_collector(proof: dict[str, Any], commit: str) -> None:
    collector = proof["collector"]
    path_value = collector["path"]
    collector_path = ROOT / path_value
    if collector_path.is_symlink() or not collector_path.is_file():
        raise ValueError("RS-G13 collector is missing")
    data = _read_and_match(
        collector_path,
        {"bytes": collector_path.stat().st_size, "sha256": collector["sha256"]},
        label="RS-G13 collector",
    )
    committed = subprocess.run(
        ["git", "show", f"{commit}:{path_value}"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if (
        committed.returncode != 0
        or len(committed.stdout) != len(data)
        or hashlib.sha256(committed.stdout).hexdigest() != collector["sha256"]
    ):
        raise ValueError("RS-G13 collector is not tied to the evidence commit")


def _validate_rs_g13(
    manifest: dict[str, Any],
    _proof: dict[str, Any],
    base: Path,
) -> set[str]:
    commands = manifest["commands"]
    artifact_paths = {
        artifact["path"] for artifact in manifest["artifacts"] if isinstance(artifact, dict)
    }
    measured: set[str] = set()
    for index, minor in enumerate(PYTHON_MINORS):
        label = f"package-py{minor.replace('.', '')}"
        directory = base / label
        proof_path = directory / "proof.json"
        try:
            package_proof = json.loads(proof_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"RS-G13 {minor} proof is invalid") from error
        measured.update(
            validate_package_proof(
                package_proof,
                expected_python=minor,
                expected_commit=manifest["commit"],
            )
        )
        _validate_collector(package_proof, manifest["commit"])
        for command_index, command in enumerate(package_proof["commands"]):
            for stream in ("stdout", "stderr"):
                relative = f"{label}/command-{command_index:02d}.{stream}"
                _read_and_match(
                    base / relative,
                    command[stream],
                    label=f"RS-G13 {minor} command {command_index} {stream}",
                )
                if command_index == 0:
                    if commands[index][stream]["path"] != relative:
                        raise ValueError("RS-G13 build command stream is not manifest-bound")
                elif relative not in artifact_paths:
                    raise ValueError("RS-G13 nested command stream is not an artifact")
        for artifact in package_proof["artifacts"].values():
            relative = f"{label}/{artifact['name']}"
            _read_and_match(
                base / relative,
                artifact,
                label=f"RS-G13 {minor} package artifact",
            )
            if relative not in artifact_paths:
                raise ValueError("RS-G13 package artifact is not manifest-bound")
        if f"{label}/proof.json" not in artifact_paths:
            raise ValueError("RS-G13 package proof is not manifest-bound")
    return measured


SPEC = GateSpec(
    gate="RS-G13",
    measurements=(
        Measurement(
            assertions=("clean-install-py311", "wheel-sdist-smoke", "cli-smoke"),
            argv=("python", "-m", "build"),
            kind="package-matrix",
            platform="python3.11",
        ),
        Measurement(
            assertions=("clean-install-py312",),
            argv=("python", "-m", "build"),
            kind="package-matrix",
            platform="python3.12",
        ),
        Measurement(
            assertions=("clean-install-py313",),
            argv=("python", "-m", "build"),
            kind="package-matrix",
            platform="python3.13",
        ),
    ),
    expected_support_sha256="0487c43e903dbd2621b94e982dd02c2ad77b319311ad6401c4fcfee9b7a7fc90",
    extra_validator=_validate_rs_g13,
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
