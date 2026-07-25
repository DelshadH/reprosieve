from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

from runsieve.capsule import load_capsule, write_capsule
from runsieve.cli import main
from runsieve.fixtures import killer_capsule


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
    output = tmp_path / "captured.runsieve"
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
    source = tmp_path / "source.runsieve"
    write_capsule(killer_capsule(), source)
    source_before = source.read_bytes()
    output_directory = tmp_path / "reduced"
    output_directory.mkdir()
    assert (
        main(
            [
                "minimize",
                str(source),
                "--output-dir",
                str(output_directory),
                "--timeout",
                "3",
                "--predicate",
                "python",
                "verify_failure.py",
            ]
        )
        == 0
    )
    assert source.read_bytes() == source_before
    outputs = list(output_directory.glob("*.runsieve"))
    assert len(outputs) == 1
    reduced_path = outputs[0]
    assert reduced_path.stem == hashlib.sha256(reduced_path.read_bytes()).hexdigest()
    reduced = load_capsule(reduced_path)
    assert len(reduced.events) <= 10
    assert reduced.metadata["provenance"]["source_sha256"] == hashlib.sha256(
        source_before
    ).hexdigest()
    assert reduced.metadata["minimality"]["is_one_minimal"] is True

    replay_path = tmp_path / "replay.json"
    assert main(["replay", str(reduced_path), "--output", str(replay_path)]) == 0
    assert "recorded-output materialization" in capfd.readouterr().out  # type: ignore[attr-defined]
    assert b'"provider_calls":0' in replay_path.read_bytes()
    assert b'"original_tool_calls":0' in replay_path.read_bytes()

    assert (
        main(
            [
                "verify-minimal",
                str(reduced_path),
                "--timeout",
                "3",
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
            ]
        )
        == 0
    )
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
    }
    proof = subprocess.run(
        [sys.executable, "reproduce.py"],
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


def test_cli_rejects_shell_strings_and_does_not_overwrite_outputs(tmp_path: Path) -> None:
    source = tmp_path / "source.runsieve"
    write_capsule(killer_capsule(), source)
    output_directory = tmp_path / "output"
    output_directory.mkdir()
    assert (
        main(
            [
                "minimize",
                str(source),
                "--output-dir",
                str(output_directory),
                "--predicate",
                "python verify_failure.py",
            ]
        )
        == 2
    )
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "user.txt").write_text("keep", encoding="utf-8")
    assert main(["export", str(source), "--output", str(occupied)]) == 2
    assert (occupied / "user.txt").read_text(encoding="utf-8") == "keep"
