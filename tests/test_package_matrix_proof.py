from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path


def test_package_collector_builds_and_clean_installs_real_artifacts(
    tmp_path: Path,
) -> None:
    module = importlib.import_module("scripts.package_matrix_proof")
    collect = getattr(module, "collect_package_proof", None)
    assert callable(collect)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    output = tmp_path / "proof"

    collect(output, commit=commit)

    proof = json.loads((output / "proof.json").read_text(encoding="utf-8"))
    gate = importlib.import_module("scripts.gates.RS_G13")
    validate = getattr(gate, "validate_package_proof", None)
    assert callable(validate)
    minor = f"{sys.version_info.major}.{sys.version_info.minor}"
    assert f"clean-install-py{minor.replace('.', '')}" in validate(
        proof,
        expected_python=minor,
        expected_commit=commit,
        expected_os=proof["runner"]["os"],
    )
    assert (output / proof["artifacts"]["wheel"]["name"]).is_file()
    assert (output / proof["artifacts"]["sdist"]["name"]).is_file()
    assert proof["commands"][4]["stdout"]["bytes"] > 0
    assert proof["reproducible_artifacts"] is True
    assert proof["source_date_epoch"].isdigit()
    assert not any("/.evidence/" in member for member in proof["members"]["sdist"])
    assert not any(
        member.endswith(("/PROGRESS.json", "/WORKLOG.md", "/.agent-state.json"))
        for member in proof["members"]["sdist"]
    )
