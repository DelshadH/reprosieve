from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from runsieve.capsule import write_capsule
from runsieve.export import export_reproduction
from runsieve.fixtures import killer_capsule
from runsieve.predicate import PredicateSpec
from tests.helpers import sample_capsule


def test_export_refuses_symlink_output_and_hostile_predicate(tmp_path: Path) -> None:
    source = tmp_path / "source.runsieve"
    write_capsule(
        killer_capsule(),
        source,
        predicate=PredicateSpec(("python", "verify_failure.py")).to_json(),
    )
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(ValueError, match="output"):
        export_reproduction(source, link)


def test_standalone_reproducer_denies_network_audit_event_without_connection(
    tmp_path: Path,
) -> None:
    capsule = killer_capsule()
    workspace = dict(capsule.workspace)
    workspace["verify_network.py"] = (
        "import sys\n"
        "try: sys.audit('socket.connect', None)\n"
        "except PermissionError: raise SystemExit(0)\n"
        "raise SystemExit(2)\n"
    )
    capsule = type(capsule)(
        schema_version=capsule.schema_version,
        trace_id=capsule.trace_id,
        events=capsule.events,
        metadata=capsule.metadata,
        workspace=workspace,
        environment=capsule.environment,
    )
    source = tmp_path / "network.runsieve"
    write_capsule(
        capsule,
        source,
        predicate=PredicateSpec(("python", "verify_network.py"), timeout_seconds=2).to_json(),
    )
    output = tmp_path / "repro"
    export_reproduction(source, output)
    result = subprocess.run(
        [sys.executable, "reproduce.py"],
        cwd=output,
        env={"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "target failure reproduced offline"


def test_standalone_reproducer_restores_declared_environment(tmp_path: Path) -> None:
    capsule = replace(
        sample_capsule(),
        workspace={
            "predicate.py": (
                "import os\n"
                "raise SystemExit(0 if os.environ.get('DEMO_FLAG') == '1' else 1)\n"
            )
        },
        environment={"DEMO_FLAG": "1"},
    )
    source = tmp_path / "environment.runsieve"
    write_capsule(
        capsule,
        source,
        predicate=PredicateSpec(("python", "predicate.py")).to_json(),
    )
    output = tmp_path / "environment-repro"
    export_reproduction(source, output)
    result = subprocess.run(
        [sys.executable, "reproduce.py"],
        cwd=output,
        env={"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "target failure reproduced offline"
