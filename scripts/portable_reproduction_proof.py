from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from reprosieve.capsule import write_capsule
from reprosieve.cli import main as reprosieve_main
from reprosieve.fixtures import killer_capsule
from reprosieve.safeio import ensure_new_path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_LIMIT = 65_536
_PROVIDER_PREFIXES = (
    "OPENAI_",
    "ANTHROPIC_",
    "AZURE_",
    "AWS_ACCESS",
    "AWS_SECRET",
    "GOOGLE_API",
    "GEMINI_",
    "COHERE_",
    "MISTRAL_",
)


def _digest(data: bytes) -> dict[str, object]:
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def build_portable_proof(
    *,
    commit: str,
    runner_os: str,
    runner_arch: str,
    exit_code: int,
    stdout: bytes,
    stderr: bytes,
    output_limit_bytes: int,
    capsule: bytes,
    reproducer: bytes,
    fresh_temporary_directory: bool,
    source_tree_present: bool,
    provider_keys_present: tuple[str, ...],
    collector_sha256: str,
) -> dict[str, Any]:
    return {
        "command": {
            "argv": ["python", "reproduce.py", "--trust-embedded-predicate"],
            "exit_code": exit_code,
            "output_limit_bytes": output_limit_bytes,
            "stderr": _digest(stderr),
            "stdout": _digest(stdout),
        },
        "commit": commit,
        "collector": {
            "path": "scripts/portable_reproduction_proof.py",
            "sha256": collector_sha256,
        },
        "export": {
            "capsule_sha256": hashlib.sha256(capsule).hexdigest(),
            "reproducer_sha256": hashlib.sha256(reproducer).hexdigest(),
        },
        "fresh_temporary_directory": fresh_temporary_directory,
        "gate": "RS-G10",
        "provider_keys_present": list(provider_keys_present),
        "runner": {"arch": runner_arch, "os": runner_os},
        "schema_version": 1,
        "source_tree_present": source_tree_present,
    }


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _clean_ci_identity() -> str:
    expected = os.environ.get("RUNSIEVE_EVIDENCE_COMMIT", "")
    head = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain=v1", "--untracked-files=all")
    if (
        len(expected) != 40
        or head.returncode
        or head.stdout.strip() != expected
        or status.returncode
        or status.stdout.strip()
    ):
        raise RuntimeError("portable proof requires the exact clean CI evidence commit")
    return expected


def _runner_identity() -> tuple[str, str]:
    declared_os = os.environ.get("RUNNER_OS", "").casefold()
    runner_os = "macos" if declared_os == "macos" else declared_os
    actual_os = platform.system().casefold()
    actual_os = "macos" if actual_os == "darwin" else actual_os
    runner_arch = os.environ.get("RUNNER_ARCH", "").casefold()
    if runner_os not in {"linux", "macos"} or actual_os != runner_os or not runner_arch:
        raise RuntimeError("portable proof runner OS or architecture is inconsistent")
    return runner_os, runner_arch


def _child_environment() -> dict[str, str]:
    environment: dict[str, str] = {}
    for name in ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "LANG", "LC_ALL"):
        value = os.environ.get(name)
        if value:
            environment[name] = value
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": "",
        }
    )
    return environment


def collect(output: Path) -> dict[str, Any]:
    commit = _clean_ci_identity()
    runner_os, runner_arch = _runner_identity()
    target = ensure_new_path(output, label="portable proof output")
    target.mkdir(mode=0o700)

    with tempfile.TemporaryDirectory(prefix="reprosieve-proof-build-") as build_temporary:
        build_root = Path(build_temporary)
        source = build_root / "source.reprosieve"
        reduced = build_root / "reduced"
        reduced.mkdir()
        write_capsule(killer_capsule(), source)
        if reprosieve_main(
            [
                "reduce",
                str(source),
                "--output-dir",
                str(reduced),
                "--timeout",
                "3",
                "--trust-embedded-predicate",
                "--predicate",
                "python",
                "verify_failure.py",
            ]
        ):
            raise RuntimeError("portable proof minimization failed")
        reduced_capsules = list(reduced.glob("*.reprosieve"))
        if len(reduced_capsules) != 1:
            raise RuntimeError("portable proof did not produce exactly one capsule")
        export = build_root / "issue-repro"
        if reprosieve_main(
            [
                "export",
                str(reduced_capsules[0]),
                "--output",
                str(export),
                "--trust-embedded-predicate",
            ]
        ):
            raise RuntimeError("portable proof export failed")

        with tempfile.TemporaryDirectory(prefix="reprosieve-clean-room-") as clean_temporary:
            clean_root = Path(clean_temporary)
            fresh = not any(clean_root.iterdir())
            clean_export = clean_root / "issue-repro"
            shutil.copytree(export, clean_export)
            source_markers = {".git", "pyproject.toml", "src"}
            source_tree_present = any(
                path.name in source_markers for path in clean_root.rglob("*")
            )
            environment = _child_environment()
            provider_keys = tuple(
                sorted(
                    name
                    for name in environment
                    if any(name.upper().startswith(prefix) for prefix in _PROVIDER_PREFIXES)
                )
            )
            completed = subprocess.run(
                [sys.executable, "reproduce.py", "--trust-embedded-predicate"],
                cwd=clean_export,
                env=environment,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=10,
                check=False,
            )
            if len(completed.stdout) + len(completed.stderr) > OUTPUT_LIMIT:
                raise RuntimeError("portable reproduction output exceeded its bound")
            capsule = (clean_export / "capsule.reprosieve").read_bytes()
            reproducer = (clean_export / "reproduce.py").read_bytes()

    proof = build_portable_proof(
        commit=commit,
        runner_os=runner_os,
        runner_arch=runner_arch,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        output_limit_bytes=OUTPUT_LIMIT,
        capsule=capsule,
        reproducer=reproducer,
        fresh_temporary_directory=fresh,
        source_tree_present=source_tree_present,
        provider_keys_present=provider_keys,
        collector_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )
    if completed.returncode:
        raise RuntimeError("portable one-command reproduction failed")
    (target / "command.stdout").write_bytes(completed.stdout)
    (target / "command.stderr").write_bytes(completed.stderr)
    (target / "capsule.reprosieve").write_bytes(capsule)
    (target / "reproduce.py").write_bytes(reproducer)
    (target / "proof.json").write_text(
        json.dumps(proof, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return proof


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 2 or arguments[0] != "--output":
        print(
            "usage: python -m scripts.portable_reproduction_proof --output DIRECTORY",
            file=sys.stderr,
        )
        return 2
    try:
        proof = collect(Path(arguments[1]))
    except (OSError, RuntimeError, ValueError) as error:
        print(f"portable proof failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {"commit": proof["commit"], "runner": proof["runner"]},
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
