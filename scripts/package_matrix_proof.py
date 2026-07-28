from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from datetime import UTC, datetime
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

from scripts.evidence import write_canonical_json

ROOT = Path(__file__).resolve().parents[1]
GIT_SHA = re.compile(r"^[a-f0-9]{40}$")
MAX_OUTPUT_BYTES = 1_000_000
VERSION = "0.1.0a2"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _output_reference(path: Path) -> dict[str, object]:
    return {"bytes": path.stat().st_size, "sha256": _sha256(path)}


def _run(
    argv: list[str],
    *,
    proof_argv: list[str],
    cwd: Path,
    output: Path,
    index: int,
    environment: dict[str, str],
) -> dict[str, object]:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=environment,
        capture_output=True,
        check=False,
        timeout=180,
    )
    stdout = completed.stdout[: MAX_OUTPUT_BYTES + 1]
    stderr = completed.stderr[: MAX_OUTPUT_BYTES + 1]
    stdout_path = output / f"command-{index:02d}.stdout"
    stderr_path = output / f"command-{index:02d}.stderr"
    stdout_path.write_bytes(stdout)
    stderr_path.write_bytes(stderr)
    if (
        completed.returncode != 0
        or len(stdout) > MAX_OUTPUT_BYTES
        or len(stderr) > MAX_OUTPUT_BYTES
    ):
        raise RuntimeError(f"package proof command {index} failed or exceeded output limits")
    return {
        "argv": proof_argv,
        "exit_code": 0,
        "stderr": _output_reference(stderr_path),
        "stdout": _output_reference(stdout_path),
    }


def _extract_git_archive(archive_path: Path, checkout: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            path = PurePosixPath(info.filename)
            if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
                raise RuntimeError("git archive contains an unsafe path")
            target = checkout.joinpath(*path.parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info))


def _artifact_members(path: Path) -> list[str]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    elif path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            names = archive.getnames()
    else:
        raise RuntimeError("package proof encountered an unsupported artifact")
    members: list[str] = []
    for name in names:
        member = PurePosixPath(name)
        if member.is_absolute() or any(part in {"", ".", ".."} for part in member.parts):
            raise RuntimeError("package artifact contains an unsafe member")
        members.append(member.as_posix())
    return sorted(members)


def _semantic_checks(wheel: Path, sdist: Path) -> dict[str, object]:
    with zipfile.ZipFile(wheel) as archive:
        metadata_names = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        entry_names = [
            name for name in archive.namelist() if name.endswith(".dist-info/entry_points.txt")
        ]
        if len(metadata_names) != 1 or len(entry_names) != 1:
            raise RuntimeError("wheel metadata or entry point inventory is invalid")
        metadata = BytesParser().parsebytes(archive.read(metadata_names[0]))
        entry_points = archive.read(entry_names[0]).decode("utf-8")
        wheel_schemas = sorted(
            name for name in archive.namelist() if name.startswith("reprosieve/schemas/")
        )
    with tarfile.open(sdist, "r:gz") as archive:
        pyprojects = [
            member for member in archive.getmembers() if member.name.endswith("/pyproject.toml")
        ]
        if len(pyprojects) != 1:
            raise RuntimeError("sdist pyproject inventory is invalid")
        stream = archive.extractfile(pyprojects[0])
        if stream is None:
            raise RuntimeError("sdist pyproject could not be read")
        project = tomllib.loads(stream.read().decode("utf-8"))["project"]
        sdist_schemas = sorted(
            member.name for member in archive.getmembers()
            if "/schemas/" in member.name and member.isfile()
        )
    requirements = metadata.get_all("Requires-Dist", [])
    unguarded = [item for item in requirements if "extra ==" not in item]
    expected_schema_names = sorted(path.name for path in (ROOT / "schemas").glob("*.json"))
    wheel_schema_names = sorted(Path(name).name for name in wheel_schemas)
    sdist_schema_names = sorted(Path(name).name for name in sdist_schemas)
    checks = {
        "core_dependencies_empty": not unguarded and project.get("dependencies") == [],
        "entry_point": "reprosieve = reprosieve.cli:main" in entry_points,
        "extras": sorted(metadata.get_all("Provides-Extra", [])),
        "name": metadata.get("Name"),
        "python_requires": metadata.get("Requires-Python"),
        "schema_names": expected_schema_names,
        "sdist_schema_parity": sdist_schema_names == expected_schema_names,
        "version": metadata.get("Version"),
        "wheel_schema_parity": wheel_schema_names == expected_schema_names,
    }
    if (
        checks["name"] != "reprosieve"
        or checks["version"] != VERSION
        or checks["python_requires"] != "<3.14,>=3.11"
        or checks["extras"] != ["dev", "openai"]
        or checks["entry_point"] is not True
        or checks["core_dependencies_empty"] is not True
        or checks["wheel_schema_parity"] is not True
        or checks["sdist_schema_parity"] is not True
        or project.get("name") != checks["name"]
        or project.get("version") != checks["version"]
        or set(str(project.get("requires-python", "")).split(","))
        != set(str(checks["python_requires"]).split(","))
    ):
        raise RuntimeError("wheel and sdist semantic metadata parity failed")
    return checks


def _write_supply_chain(
    output: Path,
    *,
    commit: str,
    epoch: str,
    wheel: Path,
    sdist: Path,
) -> dict[str, object]:
    distributions = sorted((wheel, sdist), key=lambda path: path.name)
    checksums = "".join(f"{_sha256(path)}  {path.name}\n" for path in distributions)
    checksums_path = output / "SHA256SUMS"
    checksums_path.write_text(checksums, encoding="ascii", newline="\n")
    created = datetime.fromtimestamp(int(epoch), tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    packages = [
        {
            "SPDXID": f"SPDXRef-{index}",
            "checksums": [
                {"algorithm": "SHA256", "checksumValue": _sha256(path)}
            ],
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "name": path.name,
            "versionInfo": VERSION,
        }
        for index, path in enumerate(distributions, start=1)
    ]
    sbom = {
        "SPDXID": "SPDXRef-DOCUMENT",
        "creationInfo": {
            "created": created,
            "creators": ["Tool: ReproSieve package_matrix_proof.py"],
        },
        "dataLicense": "CC0-1.0",
        "documentNamespace": f"https://github.com/DelshadH/reprosieve/spdx/{commit}",
        "name": f"reprosieve-{VERSION}-distributions",
        "packages": packages,
        "spdxVersion": "SPDX-2.3",
    }
    sbom_path = output / "reprosieve.spdx.json"
    write_canonical_json(sbom_path, sbom)
    return {
        "checksums": {
            "bytes": checksums_path.stat().st_size,
            "name": checksums_path.name,
            "sha256": _sha256(checksums_path),
        },
        "sbom": {
            "bytes": sbom_path.stat().st_size,
            "name": sbom_path.name,
            "sha256": _sha256(sbom_path),
        },
    }


def _smoke_flows(path: Path, *, require_capture: bool) -> list[str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("installed CLI smoke output is invalid") from error
    expected = [
        "help",
        "materialize",
        "reproduce-predicate",
        "reduce",
        "verify-minimal",
        "export",
        "exported-reproduce",
    ]
    if require_capture:
        expected.append("capture")
    if not isinstance(value, dict) or value.get("flows") != expected:
        raise RuntimeError("installed CLI smoke did not exercise every declared flow")
    return expected


def _commit_epoch(commit: str) -> str:
    completed = subprocess.run(
        ["git", "show", "-s", "--format=%ct", commit],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    value = completed.stdout.strip()
    if completed.returncode != 0 or not value.isdigit():
        raise RuntimeError("package proof could not resolve the commit timestamp")
    return value


def collect_package_proof(output: Path, *, commit: str) -> dict[str, object]:
    if GIT_SHA.fullmatch(commit) is None:
        raise ValueError("package proof requires a full commit SHA")
    if output.exists() or output.is_symlink():
        raise FileExistsError("package proof output already exists")
    output.mkdir(parents=True)
    environment = {
        **os.environ,
        "PIP_NO_INPUT": "1",
        "PYTHONPATH": "",
        "SOURCE_DATE_EPOCH": _commit_epoch(commit),
    }
    with tempfile.TemporaryDirectory(prefix="reprosieve-package-proof-") as temporary:
        temporary_root = Path(temporary)
        archive_path = temporary_root / "checkout.zip"
        archived = subprocess.run(
            ["git", "archive", "--format=zip", f"--output={archive_path}", commit],
            cwd=ROOT,
            capture_output=True,
            check=False,
            timeout=60,
        )
        if archived.returncode != 0 or not archive_path.is_file():
            raise RuntimeError("package proof could not create a clean Git archive")
        checkouts = (temporary_root / "checkout-a", temporary_root / "checkout-b")
        commands: list[dict[str, object]] = []
        built: list[tuple[Path, Path]] = []
        for index, checkout in enumerate(checkouts):
            checkout.mkdir()
            _extract_git_archive(archive_path, checkout)
            commands.append(
                _run(
                    [sys.executable, "-m", "build"],
                    proof_argv=["python", "-m", "build"],
                    cwd=checkout,
                    output=output,
                    index=index,
                    environment=environment,
                )
            )
            wheels = tuple((checkout / "dist").glob("*.whl"))
            sdists = tuple((checkout / "dist").glob("*.tar.gz"))
            if len(wheels) != 1 or len(sdists) != 1:
                raise RuntimeError("package proof requires exactly one wheel and one sdist")
            built.append((wheels[0], sdists[0]))
        (wheel, sdist), (rebuilt_wheel, rebuilt_sdist) = built
        if (
            wheel.read_bytes() != rebuilt_wheel.read_bytes()
            or sdist.read_bytes() != rebuilt_sdist.read_bytes()
        ):
            raise RuntimeError("package artifacts are not reproducible from the same commit")
        copied_wheel = output / wheel.name
        copied_sdist = output / sdist.name
        copied_rebuilt_wheel = output / f"rebuild-{rebuilt_wheel.name}"
        copied_rebuilt_sdist = output / f"rebuild-{rebuilt_sdist.name}"
        shutil.copyfile(wheel, copied_wheel)
        shutil.copyfile(sdist, copied_sdist)
        shutil.copyfile(rebuilt_wheel, copied_rebuilt_wheel)
        shutil.copyfile(rebuilt_sdist, copied_rebuilt_sdist)

        semantic_checks = _semantic_checks(copied_wheel, copied_sdist)
        supply_chain = _write_supply_chain(
            output,
            commit=commit,
            epoch=environment["SOURCE_DATE_EPOCH"],
            wheel=copied_wheel,
            sdist=copied_sdist,
        )
        smoke_script = checkouts[0] / "scripts" / "installed_cli_smoke.py"
        commands.append(
            _run(
                [
                    sys.executable,
                    str(smoke_script),
                    "--distribution",
                    str(copied_wheel),
                ],
                proof_argv=[
                    "python",
                    "scripts/installed_cli_smoke.py",
                    "--distribution",
                    copied_wheel.name,
                ],
                cwd=checkouts[0],
                output=output,
                index=2,
                environment=environment,
            )
        )
        wheel_flows = _smoke_flows(output / "command-02.stdout", require_capture=False)
        commands.append(
            _run(
                [
                    sys.executable,
                    str(smoke_script),
                    "--distribution",
                    str(copied_sdist),
                ],
                proof_argv=[
                    "python",
                    "scripts/installed_cli_smoke.py",
                    "--distribution",
                    copied_sdist.name,
                ],
                cwd=checkouts[0],
                output=output,
                index=3,
                environment=environment,
            )
        )
        sdist_flows = _smoke_flows(output / "command-03.stdout", require_capture=False)
        commands.append(
            _run(
                [
                    sys.executable,
                    str(smoke_script),
                    "--distribution",
                    str(copied_wheel),
                    "--with-openai",
                ],
                proof_argv=[
                    "python",
                    "scripts/installed_cli_smoke.py",
                    "--distribution",
                    copied_wheel.name,
                    "--with-openai",
                ],
                cwd=checkouts[0],
                output=output,
                index=4,
                environment=environment,
            )
        )
        capture_flows = _smoke_flows(output / "command-04.stdout", require_capture=True)
        source_tree_present = False

    proof = {
        "artifacts": {
            "rebuild_sdist": {
                "bytes": copied_rebuilt_sdist.stat().st_size,
                "name": copied_rebuilt_sdist.name,
                "sha256": _sha256(copied_rebuilt_sdist),
            },
            "rebuild_wheel": {
                "bytes": copied_rebuilt_wheel.stat().st_size,
                "name": copied_rebuilt_wheel.name,
                "sha256": _sha256(copied_rebuilt_wheel),
            },
            "sdist": {
                "bytes": copied_sdist.stat().st_size,
                "name": copied_sdist.name,
                "sha256": _sha256(copied_sdist),
            },
            "wheel": {
                "bytes": copied_wheel.stat().st_size,
                "name": copied_wheel.name,
                "sha256": _sha256(copied_wheel),
            },
        },
        "clean_install_directory": True,
        "collector": {
            "path": "scripts/package_matrix_proof.py",
            "sha256": _sha256(Path(__file__)),
        },
        "commands": commands,
        "commit": commit,
        "fresh_checkout": True,
        "gate": "RS-G13",
        "members": {
            "sdist": _artifact_members(copied_sdist),
            "wheel": _artifact_members(copied_wheel),
        },
        "installed_flows": {
            "sdist_core": sdist_flows,
            "wheel_core": wheel_flows,
            "wheel_openai": capture_flows,
        },
        "reproducible_artifacts": True,
        "semantic_checks": semantic_checks,
        "runner": {
            "arch": platform.machine().lower(),
            "os": platform.system().lower(),
            "python": platform.python_version(),
        },
        "schema_version": 1,
        "source_date_epoch": environment["SOURCE_DATE_EPOCH"],
        "source_tree_present": source_tree_present,
        "supply_chain": supply_chain,
    }
    write_canonical_json(output / "proof.json", proof)
    return proof


def _clean_commit() -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if status.returncode != 0 or status.stdout.strip():
        raise RuntimeError("package proof requires a clean committed tree")
    if commit.returncode != 0 or GIT_SHA.fullmatch(commit.stdout.strip()) is None:
        raise RuntimeError("package proof could not resolve HEAD")
    expected = os.environ.get("RUNSIEVE_EVIDENCE_COMMIT")
    if expected is not None and expected != commit.stdout.strip():
        raise RuntimeError("package proof checkout differs from the requested evidence commit")
    return commit.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 2 or arguments[0] != "--output":
        print(
            "usage: python -m scripts.package_matrix_proof --output DIRECTORY",
            file=sys.stderr,
        )
        return 2
    try:
        proof = collect_package_proof(Path(arguments[1]), commit=_clean_commit())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"package proof failed: {error}", file=sys.stderr)
        return 1
    runner = proof.get("runner")
    if not isinstance(runner, dict) or not isinstance(runner.get("python"), str):
        print("package proof failed: runner identity is invalid", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "commit": proof["commit"],
                "python": runner["python"],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
