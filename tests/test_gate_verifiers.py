from __future__ import annotations

import importlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import evidence


def test_gate_verifier_rejects_an_identity_only_manifest(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"gate":"RS-G07"}\n', encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, "-m", "scripts.gates.RS_G07", str(manifest)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 2
    assert "measured evidence" in completed.stderr


def test_every_gate_maps_each_registered_assertion_to_a_specific_measurement() -> None:
    registry = json.loads(Path("GATE_REGISTRY.json").read_text(encoding="utf-8"))
    for registered in registry["gates"]:
        module = importlib.import_module(
            f"scripts.gates.{registered['id'].replace('-', '_')}"
        )
        spec = getattr(module, "SPEC", None)
        assert spec is not None, registered["id"]
        measured = [
            assertion
            for measurement in spec.measurements
            for assertion in measurement.assertions
        ]
        assert sorted(measured) == sorted(registered["required_assertions"])
        assert len(measured) == len(set(measured))


def test_rs_g10_portable_proof_requires_measured_platform_execution() -> None:
    module = importlib.import_module("scripts.gates.RS_G10")
    validate = getattr(module, "validate_portable_proof", None)
    assert callable(validate)
    commit = "b" * 40
    proof = {
        "schema_version": 1,
        "gate": "RS-G10",
        "commit": commit,
        "collector": {
            "path": "scripts/portable_reproduction_proof.py",
            "sha256": "e" * 64,
        },
        "runner": {"os": "macos", "arch": "arm64"},
        "fresh_temporary_directory": True,
        "source_tree_present": False,
        "provider_keys_present": [],
        "command": {
            "argv": ["python", "reproduce.py"],
            "exit_code": 0,
            "output_limit_bytes": 65536,
            "stdout": {"bytes": 35, "sha256": "a" * 64},
            "stderr": {"bytes": 0, "sha256": "b" * 64},
        },
        "export": {
            "capsule_sha256": "c" * 64,
            "reproducer_sha256": "d" * 64,
        },
    }

    assert validate(proof, expected_os="macos", expected_commit=commit) == {
        "fresh-temp-run",
        "macos-one-command",
        "no-api-key",
        "no-source-repository",
    }
    for field, value in (
        ("fresh_temporary_directory", False),
        ("source_tree_present", True),
        ("provider_keys_present", ["OPENAI_API_KEY"]),
    ):
        invalid = {**proof, field: value}
        with pytest.raises(ValueError):
            validate(invalid, expected_os="macos", expected_commit=commit)
    failed = {
        **proof,
        "command": {**proof["command"], "exit_code": 1},
    }
    with pytest.raises(ValueError):
        validate(failed, expected_os="macos", expected_commit=commit)


def test_evidence_helpers_write_canonical_hashed_references(tmp_path: Path) -> None:
    blob_reference = getattr(evidence, "blob_reference", None)
    write_canonical_json = getattr(evidence, "write_canonical_json", None)
    assert callable(blob_reference)
    assert callable(write_canonical_json)

    artifact = tmp_path / "artifact.txt"
    artifact.write_bytes(b"proof\n")
    assert blob_reference(artifact, relative_to=tmp_path) == {
        "bytes": 6,
        "path": "artifact.txt",
        "sha256": "f6ed42a9d765eeb230a069bbc3d5dc346b2669594bb0b83cc6d14d5d967b8961",
    }

    manifest = tmp_path / "manifest.json"
    write_canonical_json(manifest, {"z": 1, "a": True})
    assert manifest.read_bytes() == b'{"a":true,"z":1}\n'


def test_evidence_generator_builds_the_exact_manifest_shape() -> None:
    spec = importlib.util.find_spec("scripts.generate_gate_evidence")
    assert spec is not None
    module = importlib.import_module("scripts.generate_gate_evidence")
    build_manifest = getattr(module, "build_manifest", None)
    assert callable(build_manifest)

    reference = {"bytes": 6, "path": "proof.json", "sha256": "a" * 64}
    manifest = build_manifest(
        gate="RS-G07",
        commit="b" * 40,
        started_at="2026-07-25T07:00:00Z",
        finished_at="2026-07-25T07:00:01Z",
        environment={"python": "3.13.1", "os": "test"},
        assertions=("reproduces-distinct",),
        command={
            "argv": ["python", "-m", "scripts.gates.RS_G07"],
            "exit_code": 0,
            "stdout": reference,
            "stderr": reference,
        },
        artifacts=(reference,),
        verifier={
            "argv": ["python", "-m", "scripts.gates.RS_G07"],
            "bytes": 10,
            "exit_code": 0,
            "path": "scripts/gates/RS_G07.py",
            "sha256": "c" * 64,
        },
    )
    assert set(manifest) == {
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
    assert manifest["dirty"] is False
    assert manifest["result"] == "passed"


def test_evidence_generator_derives_proof_records_from_gate_measurements() -> None:
    module = importlib.import_module("scripts.generate_gate_evidence")
    build_measurement_proof = getattr(module, "build_measurement_proof", None)
    assert callable(build_measurement_proof)
    gate = importlib.import_module("scripts.gates.RS_G07").SPEC
    commands = (
        {
            "argv": list(gate.measurements[0].argv),
            "exit_code": 0,
            "stdout": {"bytes": 4, "path": "command-00.stdout", "sha256": "a" * 64},
            "stderr": {"bytes": 0, "path": "command-00.stderr", "sha256": "b" * 64},
        },
    )

    proof = build_measurement_proof(
        gate,
        commit="c" * 40,
        commands=commands,
    )

    assert proof == {
        "schema_version": 1,
        "gate": "RS-G07",
        "commit": "c" * 40,
        "measurements": [
            {
                "argv": list(gate.measurements[0].argv),
                "assertions": list(gate.measurements[0].assertions),
                "exit_code": 0,
                "kind": "pytest",
                "platform": None,
                "stderr_sha256": "b" * 64,
                "stdout_sha256": "a" * 64,
            }
        ],
    }
