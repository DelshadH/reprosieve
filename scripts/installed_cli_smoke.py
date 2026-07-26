from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

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
_MAX_OUTPUT = 1_000_000


def _run(argv: list[str], *, cwd: Path, environment: dict[str, str]) -> None:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        timeout=180,
    )
    if (
        completed.returncode != 0
        or len(completed.stdout) > _MAX_OUTPUT
        or len(completed.stderr) > _MAX_OUTPUT
    ):
        raise RuntimeError(
            f"installed CLI flow failed: {argv[0]} {argv[1] if len(argv) > 1 else ''}"
        )


def run_installed_flows(distribution: Path, *, with_openai: bool) -> tuple[str, ...]:
    distribution = distribution.resolve(strict=True)
    if (
        not distribution.is_file()
        or distribution.is_symlink()
        or not (
            distribution.suffix == ".whl"
            or distribution.name.endswith(".tar.gz")
        )
    ):
        raise ValueError("installed CLI smoke requires a regular wheel or sdist")
    environment = {
        name: value
        for name, value in os.environ.items()
        if not any(name.upper().startswith(prefix) for prefix in _PROVIDER_PREFIXES)
    }
    environment["PIP_NO_INPUT"] = "1"
    environment["PYTHONPATH"] = ""
    flows: list[str] = []
    with tempfile.TemporaryDirectory(prefix="runsieve-installed-cli-") as temporary:
        root = Path(temporary)
        _run(
            [sys.executable, "-m", "venv", "venv"],
            cwd=root,
            environment=environment,
        )
        scripts = root / "venv" / ("Scripts" if os.name == "nt" else "bin")
        python = scripts / ("python.exe" if os.name == "nt" else "python")
        cli = scripts / ("runsieve.exe" if os.name == "nt" else "runsieve")
        requirement = (
            f"{distribution}[openai]" if with_openai else str(distribution)
        )
        install_argv = [str(python), "-m", "pip", "install"]
        if not with_openai:
            install_argv.append("--no-deps")
        install_argv.append(requirement)
        _run(install_argv, cwd=root, environment=environment)

        _run([str(cli), "--help"], cwd=root, environment=environment)
        flows.append("help")
        source = root / "source.runsieve"
        create_fixture = (
            "from runsieve.capsule import write_capsule;"
            "from runsieve.fixtures import killer_capsule;"
            f"write_capsule(killer_capsule(),r'{source}')"
        )
        _run([str(python), "-c", create_fixture], cwd=root, environment=environment)

        materialized = root / "materialized.json"
        _run(
            [str(cli), "materialize", str(source), "--output", str(materialized)],
            cwd=root,
            environment=environment,
        )
        flows.append("materialize")
        predicate_args = ["--predicate", "python", "verify_failure.py"]
        _run(
            [str(cli), "reproduce-predicate", str(source), *predicate_args],
            cwd=root,
            environment=environment,
        )
        flows.append("reproduce-predicate")
        reduced = root / "reduced"
        _run(
            [
                str(cli),
                "reduce",
                str(source),
                "--output-dir",
                str(reduced),
                *predicate_args,
            ],
            cwd=root,
            environment=environment,
        )
        flows.append("reduce")
        artifacts = tuple(reduced.glob("*.runsieve"))
        if len(artifacts) != 1:
            raise RuntimeError("installed reduce flow produced an unexpected artifact set")
        artifact = artifacts[0]
        _run(
            [str(cli), "verify-minimal", str(artifact), *predicate_args],
            cwd=root,
            environment=environment,
        )
        flows.append("verify-minimal")
        exported = root / "export"
        _run(
            [str(cli), "export", str(artifact), "--output", str(exported)],
            cwd=root,
            environment=environment,
        )
        flows.append("export")
        _run(
            [str(python), "reproduce.py"],
            cwd=exported,
            environment=environment,
        )
        flows.append("exported-reproduce")

        if with_openai:
            target = root / "capture_target.py"
            target.write_text(
                "from agents import function_span, trace\n"
                "with trace('installed capture'):\n"
                "    with function_span('probe', input='{}', output='{}'):\n"
                "        pass\n",
                encoding="utf-8",
                newline="\n",
            )
            captured = root / "captured.runsieve"
            _run(
                [
                    str(cli),
                    "capture",
                    "--output",
                    str(captured),
                    "--workspace-root",
                    str(root),
                    "--",
                    "python",
                    target.name,
                ],
                cwd=root,
                environment=environment,
            )
            flows.append("capture")
    return tuple(flows)


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    with_openai = "--with-openai" in arguments
    if with_openai:
        arguments.remove("--with-openai")
    if len(arguments) != 2 or arguments[0] not in {"--wheel", "--distribution"}:
        print(
            "usage: python -m scripts.installed_cli_smoke "
            "--distribution WHEEL_OR_SDIST "
            "[--with-openai]",
            file=sys.stderr,
        )
        return 2
    try:
        flows = run_installed_flows(Path(arguments[1]), with_openai=with_openai)
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as error:
        print(f"installed CLI smoke failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"flows": flows}, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
