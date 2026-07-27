from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SHA256 = re.compile(r"^[a-f0-9]{64}$")
GIT_SHA = re.compile(r"^[a-f0-9]{40}$")
MAX_BLOB_BYTES = 50_000_000


@dataclass(frozen=True, slots=True)
class Measurement:
    assertions: tuple[str, ...]
    argv: tuple[str, ...]
    kind: str = "pytest"
    platform: str | None = None


ExtraValidator = Callable[[dict[str, Any], dict[str, Any], Path], set[str]]


@dataclass(frozen=True, slots=True)
class GateSpec:
    gate: str
    measurements: tuple[Measurement, ...]
    expected_support_sha256: str
    extra_validator: ExtraValidator | None = None

    @property
    def assertions(self) -> tuple[str, ...]:
        return tuple(
            assertion
            for measurement in self.measurements
            for assertion in measurement.assertions
        )


def pytest_measurement(
    assertions: tuple[str, ...],
    *nodes: str,
) -> Measurement:
    if not nodes:
        raise ValueError("pytest measurement requires at least one node")
    return Measurement(
        assertions=assertions,
        argv=("python", "-m", "pytest", "-q", *nodes),
    )


def portable_measurement(
    *,
    platform: str,
    assertions: tuple[str, ...],
) -> Measurement:
    return Measurement(
        assertions=assertions,
        argv=("python", "reproduce.py", "--trust-embedded-predicate"),
        kind="portable-reproduction",
        platform=platform,
    )


def support_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _safe_blob(base: Path, reference: object, *, label: str) -> tuple[Path, bytes]:
    if not isinstance(reference, dict) or set(reference) != {"bytes", "path", "sha256"}:
        raise ValueError(f"{label} must be a complete blob reference")
    path_value = reference.get("path")
    byte_count = reference.get("bytes")
    digest = reference.get("sha256")
    if (
        not isinstance(path_value, str)
        or not path_value
        or "\\" in path_value
        or Path(path_value).is_absolute()
        or any(part in {"", ".", ".."} for part in path_value.split("/"))
        or isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or not 0 <= byte_count <= MAX_BLOB_BYTES
        or not isinstance(digest, str)
        or SHA256.fullmatch(digest) is None
    ):
        raise ValueError(f"{label} contains an invalid blob reference")
    target = base.joinpath(*path_value.split("/"))
    try:
        target.resolve(strict=True).relative_to(base.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise ValueError(f"{label} escapes the evidence directory") from error
    if target.is_symlink() or not target.is_file():
        raise ValueError(f"{label} is not a regular evidence file")
    data = target.read_bytes()
    if len(data) != byte_count or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"{label} hash or size mismatch")
    return target, data


def _measurement_record(
    *,
    measurement: Measurement,
    command: dict[str, Any],
    proof: dict[str, Any],
    base: Path,
    index: int,
) -> None:
    if set(command) != {"argv", "exit_code", "stderr", "stdout"}:
        raise ValueError(f"measured evidence command {index} has invalid fields")
    if command.get("argv") != list(measurement.argv) or command.get("exit_code") != 0:
        raise ValueError(f"measured evidence command {index} did not pass as declared")
    _stdout_path, stdout = _safe_blob(
        base,
        command.get("stdout"),
        label=f"measured evidence command {index} stdout",
    )
    _stderr_path, stderr = _safe_blob(
        base,
        command.get("stderr"),
        label=f"measured evidence command {index} stderr",
    )
    expected = {
        "argv": list(measurement.argv),
        "assertions": list(measurement.assertions),
        "exit_code": 0,
        "kind": measurement.kind,
        "platform": measurement.platform,
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
    }
    if proof != expected:
        raise ValueError(f"measured evidence record {index} does not match its command")


def require_pytest_pass(
    manifest: dict[str, Any],
    base: Path,
    index: int,
) -> None:
    command = manifest["commands"][index]
    _stdout_path, stdout = _safe_blob(
        base,
        command["stdout"],
        label=f"pytest measurement {index} stdout",
    )
    _stderr_path, stderr = _safe_blob(
        base,
        command["stderr"],
        label=f"pytest measurement {index} stderr",
    )
    text = (stdout + b"\n" + stderr).decode("utf-8", errors="replace")
    if re.search(r"\b[1-9][0-9]* passed\b", text) is None or re.search(
        r"\b(?:failed|error|errors)\b",
        text,
        flags=re.IGNORECASE,
    ):
        raise ValueError(f"pytest measurement {index} has no clean passing result")


def verify_manifest(spec: GateSpec, manifest_path: Path) -> dict[str, Any]:
    if support_sha256() != spec.expected_support_sha256:
        raise ValueError("verifier support implementation changed")
    manifest = _load_json(manifest_path, label=f"{spec.gate} evidence manifest")
    required_keys = {
        "artifacts",
        "assertions",
        "commands",
        "commit",
        "dirty",
        "environment",
        "finished_at",
        "gate",
        "project",
        "result",
        "schema_version",
        "started_at",
        "verifier",
    }
    if set(manifest) != required_keys:
        raise ValueError(f"{spec.gate}: measured evidence manifest fields are incomplete")
    commit = manifest.get("commit")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("project") != "runsieve"
        or manifest.get("gate") != spec.gate
        or manifest.get("result") != "passed"
        or manifest.get("dirty") is not False
        or not isinstance(commit, str)
        or GIT_SHA.fullmatch(commit) is None
    ):
        raise ValueError(f"{spec.gate}: measured evidence identity is invalid")
    if not spec.measurements or not spec.assertions or len(spec.assertions) != len(
        set(spec.assertions)
    ):
        raise ValueError(f"{spec.gate}: gate-specific measurement mapping is invalid")

    assertions = manifest.get("assertions")
    expected_assertions = [
        {"id": assertion, "passed": True} for assertion in spec.assertions
    ]
    if assertions != expected_assertions:
        raise ValueError(f"{spec.gate}: manifest assertions are not measurement-derived")

    commands = manifest.get("commands")
    if not isinstance(commands, list) or len(commands) != len(spec.measurements):
        raise ValueError(f"{spec.gate}: measured evidence commands are incomplete")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError(f"{spec.gate}: measured evidence artifacts are missing")
    base = manifest_path.parent
    artifact_data: dict[str, bytes] = {}
    for index, artifact in enumerate(artifacts):
        target, data = _safe_blob(
            base,
            artifact,
            label=f"measured evidence artifact {index}",
        )
        artifact_data[target.relative_to(base).as_posix()] = data
    proof_data = artifact_data.get("proof.json")
    if proof_data is None:
        raise ValueError(f"{spec.gate}: measured evidence proof.json is missing")
    try:
        proof_document = json.loads(proof_data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{spec.gate}: measured evidence proof.json is invalid") from error
    if not isinstance(proof_document, dict):
        raise ValueError(f"{spec.gate}: measured evidence proof must be an object")
    proof_records = proof_document.get("measurements")
    if (
        set(proof_document) != {"commit", "gate", "measurements", "schema_version"}
        or proof_document.get("schema_version") != 1
        or proof_document.get("gate") != spec.gate
        or proof_document.get("commit") != commit
        or not isinstance(proof_records, list)
        or len(proof_records) != len(spec.measurements)
    ):
        raise ValueError(f"{spec.gate}: measured evidence proof identity is invalid")
    for index, measurement in enumerate(spec.measurements):
        record = proof_records[index]
        command = commands[index]
        if not isinstance(record, dict) or not isinstance(command, dict):
            raise ValueError(f"{spec.gate}: measured evidence record {index} is invalid")
        _measurement_record(
            measurement=measurement,
            command=command,
            proof=record,
            base=base,
            index=index,
        )

    if spec.extra_validator is None:
        raise ValueError(f"{spec.gate}: gate-specific assertion derivation is missing")
    measured = spec.extra_validator(manifest, proof_document, base)
    if measured != set(spec.assertions):
        raise ValueError(f"{spec.gate}: not every assertion has measured evidence")
    return {
        "assertions": [
            {"id": assertion, "passed": True} for assertion in spec.assertions
        ],
        "gate": spec.gate,
        "passed": True,
    }


def verify_gate(spec: GateSpec) -> int:
    if len(sys.argv) != 2:
        print(f"{spec.gate}: expected one evidence-manifest path", file=sys.stderr)
        return 2
    try:
        report = verify_manifest(spec, Path(sys.argv[1]))
    except ValueError as error:
        print(f"{spec.gate}: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0
