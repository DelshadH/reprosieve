from __future__ import annotations

import json
from pathlib import Path

from scripts.gates.RS_G10 import SPEC
from scripts.generate_gate_evidence import _portable_inputs
from scripts.portable_reproduction_proof import build_portable_proof


def test_portable_proof_records_exact_runner_command_and_artifact_identity() -> None:
    proof = build_portable_proof(
        commit="a" * 40,
        runner_os="macos",
        runner_arch="arm64",
        exit_code=0,
        stdout=b"target failure reproduced offline\n",
        stderr=b"",
        output_limit_bytes=65_536,
        capsule=b"capsule",
        reproducer=b"reproducer",
        fresh_temporary_directory=True,
        source_tree_present=False,
        provider_keys_present=(),
        collector_sha256="e" * 64,
    )

    assert proof["runner"] == {"os": "macos", "arch": "arm64"}
    assert proof["command"]["argv"] == [
        "python",
        "reproduce.py",
        "--trust-embedded-predicate",
    ]
    assert proof["command"]["exit_code"] == 0
    assert proof["command"]["stdout"]["bytes"] == 34
    assert proof["collector"]["sha256"] == "e" * 64
    assert proof["export"]["capsule_sha256"] != proof["export"]["reproducer_sha256"]
    assert proof["provider_keys_present"] == []


def test_portable_command_streams_are_not_duplicated_as_artifacts(
    tmp_path: Path,
) -> None:
    commit = "a" * 40
    inputs: list[Path] = []
    for runner_os in ("linux", "macos"):
        directory = tmp_path / runner_os
        directory.mkdir()
        stdout = b"target failure reproduced offline\n"
        stderr = b""
        capsule = f"{runner_os}-capsule".encode()
        reproducer = f"{runner_os}-reproducer".encode()
        proof = build_portable_proof(
            commit=commit,
            runner_os=runner_os,
            runner_arch="arm64",
            exit_code=0,
            stdout=stdout,
            stderr=stderr,
            output_limit_bytes=65_536,
            capsule=capsule,
            reproducer=reproducer,
            fresh_temporary_directory=True,
            source_tree_present=False,
            provider_keys_present=(),
            collector_sha256="e" * 64,
        )
        (directory / "command.stdout").write_bytes(stdout)
        (directory / "command.stderr").write_bytes(stderr)
        (directory / "capsule.reprosieve").write_bytes(capsule)
        (directory / "reproduce.py").write_bytes(reproducer)
        (directory / "proof.json").write_text(json.dumps(proof), encoding="utf-8")
        inputs.append(directory)
    output = tmp_path / "evidence"
    output.mkdir()

    commands, artifacts = _portable_inputs(
        SPEC,
        commit=commit,
        directory=output,
        proof_inputs=tuple(inputs),
    )

    command_paths = {
        command[stream]["path"]
        for command in commands
        for stream in ("stdout", "stderr")
    }
    artifact_paths = {artifact["path"] for artifact in artifacts}
    assert command_paths.isdisjoint(artifact_paths)
