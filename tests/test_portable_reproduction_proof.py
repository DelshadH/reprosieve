from __future__ import annotations

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
    assert proof["command"]["argv"] == ["python", "reproduce.py"]
    assert proof["command"]["exit_code"] == 0
    assert proof["command"]["stdout"]["bytes"] == 34
    assert proof["collector"]["sha256"] == "e" * 64
    assert proof["export"]["capsule_sha256"] != proof["export"]["reproducer_sha256"]
    assert proof["provider_keys_present"] == []
