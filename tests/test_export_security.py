from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

import reprosieve.export as export_module
from reprosieve.capsule import (
    capsule_bytes,
    load_capsule,
    read_capsule_document,
    write_capsule,
)
from reprosieve.export import export_reproduction
from reprosieve.fixtures import killer_capsule
from reprosieve.predicate import PredicateSpec
from tests.helpers import rewrite_capsule_members, sample_capsule


def test_standalone_reproducer_requires_explicit_embedded_predicate_trust(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.reprosieve"
    write_capsule(
        killer_capsule(),
        source,
        predicate=PredicateSpec(("python", "verify_failure.py")).to_json(),
    )
    output = tmp_path / "repro"
    export_reproduction(source, output)

    result = subprocess.run(
        [sys.executable, "reproduce.py"],
        cwd=output,
        env={
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        },
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 2
    assert "untrusted embedded Python" in result.stderr
    assert "--trust-embedded-predicate" in result.stderr


def test_export_refuses_symlink_output_and_hostile_predicate(tmp_path: Path) -> None:
    source = tmp_path / "source.reprosieve"
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


def test_export_copies_the_same_capsule_snapshot_that_it_validated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.reprosieve"
    write_capsule(
        killer_capsule(),
        source,
        predicate=PredicateSpec(("python", "verify_failure.py")).to_json(),
    )
    validated_bytes = source.read_bytes()
    replacement = b"unvalidated replacement"
    original_ensure_new_path = export_module.ensure_new_path

    def swap_source_before_output(path: str | Path, *, label: str) -> Path:
        source.write_bytes(replacement)
        return original_ensure_new_path(path, label=label)

    monkeypatch.setattr(export_module, "ensure_new_path", swap_source_before_output)
    output = export_reproduction(source, tmp_path / "repro")
    exported = output / "capsule.reprosieve"

    assert exported.read_bytes() == validated_bytes
    assert load_capsule(exported).trace_id == killer_capsule().trace_id


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
    source = tmp_path / "network.reprosieve"
    write_capsule(
        capsule,
        source,
        predicate=PredicateSpec(("python", "verify_network.py"), timeout_seconds=2).to_json(),
    )
    output = tmp_path / "repro"
    export_reproduction(source, output)
    result = subprocess.run(
        [sys.executable, "reproduce.py", "--trust-embedded-predicate"],
        cwd=output,
        env={"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "target failure reproduced offline"


def test_standalone_reproducer_denies_exec_audit_events(tmp_path: Path) -> None:
    capsule = replace(
        sample_capsule(),
        workspace={
            "predicate.py": (
                "import sys\n"
                "try:\n"
                "    sys.audit('os.exec', sys.executable, [sys.executable], {})\n"
                "except PermissionError:\n"
                "    raise SystemExit(0)\n"
                "raise SystemExit(1)\n"
            )
        },
    )
    source = tmp_path / "exec.reprosieve"
    write_capsule(
        capsule,
        source,
        predicate=PredicateSpec(("python", "predicate.py")).to_json(),
    )
    output = export_reproduction(source, tmp_path / "exec-repro")
    result = subprocess.run(
        [sys.executable, "reproduce.py", "--trust-embedded-predicate"],
        cwd=output,
        env={
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        },
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
    source = tmp_path / "environment.reprosieve"
    write_capsule(
        capsule,
        source,
        predicate=PredicateSpec(("python", "predicate.py")).to_json(),
    )
    output = tmp_path / "environment-repro"
    export_reproduction(source, output)
    result = subprocess.run(
        [sys.executable, "reproduce.py", "--trust-embedded-predicate"],
        cwd=output,
        env={"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "target failure reproduced offline"


def test_standalone_reproducer_rejects_json_rejected_by_the_main_loader(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.reprosieve"
    write_capsule(
        killer_capsule(),
        source,
        predicate=PredicateSpec(("python", "verify_failure.py")).to_json(),
    )
    output = export_reproduction(source, tmp_path / "repro")
    capsule_path = output / "capsule.reprosieve"
    data = capsule_path.read_bytes()
    with zipfile.ZipFile(capsule_path) as archive:
        events = archive.read("events/v1.json")
    duplicate_key_events = events.replace(b"[{", b'[{\"kind\":\"run\",', 1)
    capsule_path.write_bytes(
        rewrite_capsule_members(
            data,
            {"events/v1.json": duplicate_key_events},
        )
    )

    with pytest.raises(ValueError, match="duplicate object keys"):
        load_capsule(capsule_path)
    result = subprocess.run(
        [sys.executable, "reproduce.py", "--trust-embedded-predicate"],
        cwd=output,
        env={
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        },
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 2
    assert result.stderr.strip() == "reproduction capsule invalid"


def test_standalone_reproducer_rejects_non_utf8_json_like_the_main_loader(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.reprosieve"
    spec = PredicateSpec(("python", "verify_failure.py")).to_json()
    write_capsule(killer_capsule(), source, predicate=spec)
    output = export_reproduction(source, tmp_path / "repro")
    capsule_path = output / "capsule.reprosieve"
    valid_data = capsule_path.read_bytes()
    canonical_predicate = (
        json.dumps(spec, separators=(",", ":"), sort_keys=True) + "\n"
    )

    for hostile_predicate in (
        canonical_predicate.encode("utf-16"),
        b"\xef\xbb\xbf" + canonical_predicate.encode("utf-8"),
    ):
        capsule_path.write_bytes(
            rewrite_capsule_members(
                valid_data,
                {"predicate.json": hostile_predicate},
            )
        )
        with pytest.raises(ValueError):
            read_capsule_document(capsule_path, "predicate.json")
        result = subprocess.run(
            [sys.executable, "reproduce.py", "--trust-embedded-predicate"],
            cwd=output,
            env={
                "PATH": os.environ.get("PATH", ""),
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            },
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert result.returncode == 2
        assert result.stderr.strip() == "reproduction capsule invalid"


def test_main_loader_and_export_reject_duplicate_workspace_index_paths(
    tmp_path: Path,
) -> None:
    source = tmp_path / "duplicate-workspace-index.reprosieve"
    write_capsule(
        killer_capsule(),
        source,
        predicate=PredicateSpec(("python", "verify_failure.py")).to_json(),
    )
    source.write_bytes(
        rewrite_capsule_members(
            source.read_bytes(),
            {
                "workspace/index.json": (
                    b'["verify_failure.py","verify_failure.py"]\n'
                )
            },
        )
    )

    with pytest.raises(ValueError, match="workspace path collision"):
        load_capsule(source)
    with pytest.raises(ValueError, match="workspace path collision"):
        export_reproduction(source, tmp_path / "repro")


def test_standalone_rejects_oversized_metadata_keys_like_the_main_loader(
    tmp_path: Path,
) -> None:
    source = tmp_path / "oversized-metadata-key.reprosieve"
    write_capsule(
        killer_capsule(),
        source,
        predicate=PredicateSpec(("python", "verify_failure.py")).to_json(),
    )
    output = export_reproduction(source, tmp_path / "repro")
    capsule_path = output / "capsule.reprosieve"
    hostile_metadata = json.dumps({"x" * (4 * 1024 * 1024 + 1): True}).encode()
    capsule_path.write_bytes(
        rewrite_capsule_members(
            capsule_path.read_bytes(),
            {"metadata.json": hostile_metadata},
        )
    )

    with pytest.raises(ValueError, match="key limit"):
        load_capsule(capsule_path)
    result = subprocess.run(
        [sys.executable, "reproduce.py", "--trust-embedded-predicate"],
        cwd=output,
        env={
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        },
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 2
    assert result.stderr.strip() == "reproduction capsule invalid"


def test_loader_and_export_eagerly_reject_malformed_required_json(
    tmp_path: Path,
) -> None:
    source = tmp_path / "malformed-redaction.reprosieve"
    write_capsule(
        killer_capsule(),
        source,
        predicate=PredicateSpec(("python", "verify_failure.py")).to_json(),
    )
    source.write_bytes(
        rewrite_capsule_members(
            source.read_bytes(),
            {"redaction.json": b"\xff"},
        )
    )

    with pytest.raises(ValueError, match="redaction"):
        load_capsule(source)
    with pytest.raises(ValueError, match="redaction"):
        export_reproduction(source, tmp_path / "repro")


def test_standalone_reproducer_rejects_members_outside_the_public_schema(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.reprosieve"
    write_capsule(
        killer_capsule(),
        source,
        predicate=PredicateSpec(("python", "verify_failure.py")).to_json(),
    )
    output = export_reproduction(source, tmp_path / "repro")
    capsule_path = output / "capsule.reprosieve"
    capsule_path.write_bytes(
        rewrite_capsule_members(
            capsule_path.read_bytes(),
            {"unexpected/opaque.bin": b"manifest-covered but undefined"},
        )
    )

    result = subprocess.run(
        [sys.executable, "reproduce.py", "--trust-embedded-predicate"],
        cwd=output,
        env={
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        },
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 2
    assert result.stderr.strip() == "reproduction capsule invalid"


def test_standalone_reproducer_enforces_the_main_event_schema(tmp_path: Path) -> None:
    source = tmp_path / "source.reprosieve"
    write_capsule(
        killer_capsule(),
        source,
        predicate=PredicateSpec(("python", "verify_failure.py")).to_json(),
    )
    output = export_reproduction(source, tmp_path / "repro")
    capsule_path = output / "capsule.reprosieve"
    with zipfile.ZipFile(capsule_path) as archive:
        events = json.loads(archive.read("events/v1.json"))
    events[0]["unexpected"] = True
    capsule_path.write_bytes(
        rewrite_capsule_members(
            capsule_path.read_bytes(),
            {
                "events/v1.json": (
                    json.dumps(events, separators=(",", ":"), sort_keys=True) + "\n"
                ).encode()
            },
        )
    )

    result = subprocess.run(
        [sys.executable, "reproduce.py", "--trust-embedded-predicate"],
        cwd=output,
        env={
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        },
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 2
    assert result.stderr.strip() == "reproduction capsule invalid"


def test_standalone_reproducer_matches_main_graph_and_workspace_validation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.reprosieve"
    write_capsule(
        killer_capsule(),
        source,
        predicate=PredicateSpec(("python", "verify_failure.py")).to_json(),
    )
    output = export_reproduction(source, tmp_path / "repro")
    capsule_path = output / "capsule.reprosieve"
    valid_data = capsule_path.read_bytes()
    with zipfile.ZipFile(capsule_path) as archive:
        events = json.loads(archive.read("events/v1.json"))
    events[-1]["dependencies"] = ["missing-producer"]
    invalid_graph = rewrite_capsule_members(
        valid_data,
        {
            "events/v1.json": (
                json.dumps(events, separators=(",", ":"), sort_keys=True) + "\n"
            ).encode()
        },
    )
    undeclared_workspace = rewrite_capsule_members(
        valid_data,
        {"workspace/files/undeclared.py": b"raise SystemExit(0)\n"},
    )

    for hostile_data in (invalid_graph, undeclared_workspace):
        capsule_path.write_bytes(hostile_data)
        with pytest.raises(ValueError):
            load_capsule(capsule_path)
        result = subprocess.run(
            [sys.executable, "reproduce.py", "--trust-embedded-predicate"],
            cwd=output,
            env={
                "PATH": os.environ.get("PATH", ""),
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            },
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert result.returncode == 2
        assert result.stderr.strip() == "reproduction capsule invalid"


def test_export_rejects_deferred_application_replay_declarations(
    tmp_path: Path,
) -> None:
    capsule = replace(
        sample_capsule(),
        metadata={
            **sample_capsule().metadata,
            "application_replay": {
                "protocol": "reprosieve-recorded-v1",
                "argv": ["python", "replay_application.py"],
            },
        },
        workspace={
            "replay_application.py": (
                "import json, os, pathlib\n"
                "from reprosieve_replay_adapter import next_tool_output\n"
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
    source = tmp_path / "application.reprosieve"
    write_capsule(
        capsule,
        source,
        predicate=PredicateSpec(("python", "predicate.py")).to_json(),
    )
    output = tmp_path / "application-repro"
    with pytest.raises(ValueError, match="application replay is not supported"):
        export_reproduction(source, output)


def test_export_readme_never_claims_application_replay(tmp_path: Path) -> None:
    source = tmp_path / "source.reprosieve"
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
    assert "arbitrary code" in readme
    assert "not an os sandbox" in readme
    assert "--trust-embedded-predicate" in readme


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
    source = tmp_path / "source.reprosieve"
    write_capsule(capsule, source, predicate=valid)
    output = export_reproduction(source, tmp_path / "repro")
    hostile = {**valid, field: value}
    (output / "capsule.reprosieve").write_bytes(
        capsule_bytes(capsule, predicate=hostile)
    )
    result = subprocess.run(
        [sys.executable, "reproduce.py", "--trust-embedded-predicate"],
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
