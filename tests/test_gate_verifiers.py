from __future__ import annotations

import importlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from scripts import evidence


def test_tri_state_gate_runs_its_real_proof_and_reports_registered_assertions(
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

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["gate"] == "RS-G07"
    assert report["passed"] is True
    assert {item["id"] for item in report["assertions"]} == {
        "reproduces-distinct",
        "absent-distinct",
        "invalid-distinct",
        "timeout-invalid",
        "signal-invalid",
    }


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
