from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

import reprosieve.capsule as capsule_module
from reprosieve.capsule import load_capsule, write_capsule
from reprosieve.cli import build_parser, main
from reprosieve.fixtures import killer_capsule


def test_demo_runs_full_synthetic_flow_without_user_trust_flag(
    tmp_path: Path,
    capfd: object,
) -> None:
    output = tmp_path / "demo"

    assert main(["demo", "--output-dir", str(output)]) == 0

    captured = capfd.readouterr()  # type: ignore[attr-defined]
    assert "synthetic fixture: killer-247" in captured.out
    assert "events: 247 -> 5" in captured.out
    assert "predicate: reproduces" in captured.out
    assert "minimality: 1-minimal" in captured.out
    assert "elapsed:" in captured.out
    assert (output / "source.reprosieve").is_file()
    reduced = tuple((output / "reduced").glob("*.reprosieve"))
    reports = tuple((output / "reduced").glob("*.report.json"))
    assert len(reduced) == 1
    assert len(reports) == 1
    assert (output / "materialized.json").is_file()
    assert (output / "issue-repro" / "reproduce.py").is_file()
    summary = json.loads((output / "demo-summary.json").read_text(encoding="utf-8"))
    assert summary == {
        "elapsed_seconds": summary["elapsed_seconds"],
        "exported_reproduction_exit_code": 0,
        "final_events": 5,
        "format": "reprosieve-demo-summary",
        "format_version": 1,
        "minimality": "1-minimal",
        "original_events": 247,
        "predicate_result": "reproduces",
        "synthetic": True,
    }


def test_demo_never_overwrites_an_existing_output_directory(tmp_path: Path) -> None:
    output = tmp_path / "occupied"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")

    assert main(["demo", "--output-dir", str(output)]) == 2
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert tuple(output.iterdir()) == (sentinel,)


def test_demo_without_output_directory_cleans_its_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    assert main(["demo"]) == 0

    assert not tuple(tmp_path.glob("reprosieve-demo-*"))


def test_demo_help_explains_why_user_trust_is_not_required(capfd: object) -> None:
    with pytest.raises(SystemExit) as stopped:
        build_parser().parse_args(["demo", "--help"])

    assert stopped.value.code == 0
    output = " ".join(capfd.readouterr().out.split())  # type: ignore[attr-defined]
    assert "accepts no external capsule or predicate" in output
    assert "does not require --trust-embedded-predicate" in output


@pytest.mark.parametrize(
    "arguments",
    [
        [
            "reduce",
            "capsule.reprosieve",
            "--output-dir",
            "out",
            "--predicate",
            "python",
            "predicate.py",
        ],
        [
            "reproduce-predicate",
            "capsule.reprosieve",
            "--predicate",
            "python",
            "predicate.py",
        ],
        [
            "verify-minimal",
            "capsule.reprosieve",
            "--predicate",
            "python",
            "predicate.py",
        ],
        ["export", "capsule.reprosieve", "--output", "out"],
    ],
)
def test_capsule_predicate_commands_require_explicit_trust(
    arguments: list[str],
) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(arguments)


def test_capture_runs_real_sdk_target_and_redacts_process_output(
    tmp_path: Path,
    monkeypatch: object,
    capfd: object,
) -> None:
    canary = "CAPTURE-PROCESS-CANARY"
    target = tmp_path / "agent_target.py"
    target.write_text(
        "import os\n"
        "from agents import function_span, trace\n"
        "secret=os.environ['CAPTURE_CANARY']\n"
        "print(secret)\n"
        "with trace('capture cli fixture', metadata={'authorization': secret}):\n"
        "    with function_span('probe', input='{}', "
        "output='{\"failure\":\"needle\"}'):\n"
        "        pass\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CAPTURE_CANARY", canary)  # type: ignore[attr-defined]
    output = tmp_path / "captured.reprosieve"
    exit_code = main(
        [
            "capture",
            "--output",
            str(output),
            "--workspace-root",
            str(tmp_path),
            "--canary-env",
            "CAPTURE_CANARY",
            "--",
            sys.executable,
            str(target),
        ]
    )
    captured = capfd.readouterr()  # type: ignore[attr-defined]
    assert exit_code == 0
    assert output.is_file()
    assert canary.encode() not in output.read_bytes()
    assert canary not in captured.out
    assert canary not in captured.err
    assert any(event.kind == "tool_result" for event in load_capsule(output).events)


def test_minimize_verify_replay_and_one_command_export(tmp_path: Path, capfd: object) -> None:
    source = tmp_path / "source.reprosieve"
    write_capsule(killer_capsule(), source)
    source_before = source.read_bytes()
    output_directory = tmp_path / "reduced"
    output_directory.mkdir()
    assert (
        main(
            [
                "reduce",
                str(source),
                "--output-dir",
                str(output_directory),
                "--timeout",
                "3",
                "--trust-embedded-predicate",
                "--predicate",
                "python",
                "verify_failure.py",
            ]
        )
        == 0
    )
    assert source.read_bytes() == source_before
    outputs = list(output_directory.glob("*.reprosieve"))
    assert len(outputs) == 1
    reduced_path = outputs[0]
    report_paths = list(output_directory.glob("*.report.json"))
    assert len(report_paths) == 1
    reduction_report = json.loads(report_paths[0].read_text(encoding="utf-8"))
    report_before = report_paths[0].read_bytes()
    assert reduction_report["artifact_sha256"] == reduced_path.stem
    assert reduction_report["predicate"]["trials"] == 1
    assert reduction_report["final_predicate"]["trials"] == 1
    assert len(reduction_report["final_predicate"]["attempts"]) == 1
    assert reduction_report["minimality"]["is_one_minimal"] is True
    assert reduced_path.stem == hashlib.sha256(reduced_path.read_bytes()).hexdigest()
    reduced = load_capsule(reduced_path)
    assert len(reduced.events) <= 10
    assert reduced.metadata["provenance"]["source_sha256"] == hashlib.sha256(
        source_before
    ).hexdigest()
    assert reduced.metadata["minimality"]["is_one_minimal"] is True
    assert "offline_proof" not in reduced.metadata
    assert (
        main(
            [
                "reduce",
                str(source),
                "--output-dir",
                str(output_directory),
                "--timeout",
                "3",
                "--trust-embedded-predicate",
                "--predicate",
                "python",
                "verify_failure.py",
            ]
        )
        == 0
    )
    assert report_paths[0].read_bytes() == report_before

    replay_path = tmp_path / "materialized.json"
    assert main(["materialize", str(reduced_path), "--output", str(replay_path)]) == 0
    assert "recorded-output materialization" in capfd.readouterr().out  # type: ignore[attr-defined]
    assert b'"provider_calls"' not in replay_path.read_bytes()
    assert b'"original_tool_calls"' not in replay_path.read_bytes()

    assert (
        main(
            [
                "verify-minimal",
                str(reduced_path),
                "--timeout",
                "3",
                "--trust-embedded-predicate",
                "--predicate",
                "python",
                "verify_failure.py",
            ]
        )
        == 0
    )

    export_directory = tmp_path / "issue-repro"
    assert (
        main(
            [
                "export",
                str(reduced_path),
                "--output",
                str(export_directory),
                "--trust-embedded-predicate",
            ]
        )
        == 0
    )
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
    }
    proof = subprocess.run(
        [sys.executable, "reproduce.py", "--trust-embedded-predicate"],
        cwd=export_directory,
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert proof.returncode == 0, proof.stderr
    assert proof.stdout.strip() == "target failure reproduced offline"
    assert "OPENAI_API_KEY" not in proof.stdout + proof.stderr
    assert not any("__pycache__" in str(path) for path in export_directory.rglob("*"))
    capfd.readouterr()  # type: ignore[attr-defined]


def test_reduce_uses_one_immutable_source_capsule_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.reprosieve"
    write_capsule(killer_capsule(), source)
    original_read = capsule_module.read_regular_file_bounded
    source_reads = 0

    def count_source_reads(
        path: str | Path,
        *,
        max_bytes: int,
        label: str,
    ) -> bytes:
        nonlocal source_reads
        if Path(path) == source:
            source_reads += 1
        return original_read(path, max_bytes=max_bytes, label=label)

    monkeypatch.setattr(
        capsule_module,
        "read_regular_file_bounded",
        count_source_reads,
    )

    assert (
        main(
            [
                "reduce",
                str(source),
                "--output-dir",
                str(tmp_path / "reduced"),
                "--timeout",
                "3",
                "--trust-embedded-predicate",
                "--predicate",
                "python",
                "verify_failure.py",
            ]
        )
        == 0
    )
    assert source_reads == 1


def test_reproduce_predicate_runs_the_declared_offline_predicate(tmp_path: Path) -> None:
    source = tmp_path / "source.reprosieve"
    write_capsule(killer_capsule(), source)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "reprosieve.cli",
            "reproduce-predicate",
            str(source),
            "--trust-embedded-predicate",
            "--predicate",
            "python",
            "verify_failure.py",
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert '"result":"reproduces"' in result.stdout
    assert '"reason":"exit_0"' in result.stdout


def test_replay_alias_is_explicitly_deprecated(tmp_path: Path) -> None:
    source = tmp_path / "source.reprosieve"
    output = tmp_path / "materialized.json"
    write_capsule(killer_capsule(), source)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "reprosieve.cli",
            "replay",
            str(source),
            "--output",
            str(output),
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "deprecated" in result.stderr.casefold()
    assert output.is_file()


def test_minimize_alias_is_explicitly_deprecated(tmp_path: Path) -> None:
    source = tmp_path / "source.reprosieve"
    output_directory = tmp_path / "reduced"
    write_capsule(killer_capsule(), source)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "reprosieve.cli",
            "minimize",
            str(source),
            "--output-dir",
            str(output_directory),
            "--trust-embedded-predicate",
            "--predicate",
            "python",
            "verify_failure.py",
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "deprecated" in result.stderr.casefold()
    assert list(output_directory.glob("*.reprosieve"))


def test_cli_rejects_shell_strings_and_does_not_overwrite_outputs(tmp_path: Path) -> None:
    source = tmp_path / "source.reprosieve"
    write_capsule(killer_capsule(), source)
    output_directory = tmp_path / "output"
    output_directory.mkdir()
    assert (
        main(
            [
                "reduce",
                str(source),
                "--output-dir",
                str(output_directory),
                "--trust-embedded-predicate",
                "--predicate",
                "python verify_failure.py",
            ]
        )
        == 2
    )
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "user.txt").write_text("keep", encoding="utf-8")
    assert (
        main(
            [
                "export",
                str(source),
                "--output",
                str(occupied),
                "--trust-embedded-predicate",
            ]
        )
        == 2
    )
    assert (occupied / "user.txt").read_text(encoding="utf-8") == "keep"
