from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from runsieve.capsule import capsule_bytes, write_capsule
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


def test_export_rejects_deferred_application_replay_declarations(
    tmp_path: Path,
) -> None:
    capsule = replace(
        sample_capsule(),
        metadata={
            **sample_capsule().metadata,
            "application_replay": {
                "protocol": "runsieve-recorded-v1",
                "argv": ["python", "replay_application.py"],
            },
        },
        workspace={
            "replay_application.py": (
                "import json, os, pathlib\n"
                "from runsieve_replay_adapter import next_tool_output\n"
                "print('RUNSIEVE-SYNTHETIC-OUTPUT-CANARY')\n"
                "persisted = list(pathlib.Path('.').glob('.*.stdout')) + "
                "list(pathlib.Path('.').glob('.*.stderr'))\n"
                "failure = next_tool_output('probe')['failure'] if not persisted "
                "else 'output-persisted'\n"
                "result = {'failure': failure}\n"
                "pathlib.Path(os.environ['RUNSIEVE_APPLICATION_RESULT']).write_text("
                "json.dumps(result), encoding='utf-8')\n"
            ),
            "predicate.py": (
                "import json, os, pathlib\n"
                "result=json.loads(pathlib.Path("
                "os.environ['RUNSIEVE_APPLICATION_RESULT']).read_text())\n"
                "raise SystemExit(0 if result.get('failure') == 'needle' else 1)\n"
            ),
        },
    )
    source = tmp_path / "application.runsieve"
    write_capsule(
        capsule,
        source,
        predicate=PredicateSpec(("python", "predicate.py")).to_json(),
    )
    output = tmp_path / "application-repro"
    with pytest.raises(ValueError, match="application replay is not supported"):
        export_reproduction(source, output)


def test_export_readme_never_claims_application_replay(tmp_path: Path) -> None:
    source = tmp_path / "source.runsieve"
    write_capsule(
        killer_capsule(),
        source,
        predicate=PredicateSpec(("python", "verify_failure.py")).to_json(),
    )
    output = export_reproduction(source, tmp_path / "repro")
    readme = (output / "README.md").read_text(encoding="utf-8").casefold()
    assert "application adapter" not in readme
    assert "application replay" not in readme
    assert "recorded" in readme
    assert "predicate" in readme


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("timeout_seconds", 1_000_000),
        ("output_limit_bytes", 1_000_000_000),
        ("process_limit", 1_000_000_000),
        ("trials", 101),
        ("required_reproductions", 2),
    ],
)
def test_standalone_reproducer_rejects_hostile_resource_policy_before_execution(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    capsule = replace(
        sample_capsule(),
        workspace={"predicate.py": "import time\ntime.sleep(30)\nraise SystemExit(0)\n"},
    )
    valid = PredicateSpec(("python", "predicate.py"), timeout_seconds=1).to_json()
    source = tmp_path / "source.runsieve"
    write_capsule(capsule, source, predicate=valid)
    output = export_reproduction(source, tmp_path / "repro")
    hostile = {**valid, field: value}
    (output / "capsule.runsieve").write_bytes(
        capsule_bytes(capsule, predicate=hostile)
    )
    result = subprocess.run(
        [sys.executable, "reproduce.py"],
        cwd=output,
        env={
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        },
        capture_output=True,
        text=True,
        timeout=3,
        check=False,
    )
    assert result.returncode == 2
    assert result.stderr.strip() == "reproduction capsule invalid"
