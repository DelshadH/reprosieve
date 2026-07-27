from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from scripts.gates._verify import (
    GateSpec,
    Measurement,
    verify_gate,
)

SHA256 = re.compile(r"^[a-f0-9]{64}$")
GIT_SHA = re.compile(r"^[a-f0-9]{40}$")
PLATFORMS = ("linux", "macos")
ROOT = Path(__file__).resolve().parents[2]
COLLECTOR_PATH = "scripts/portable_reproduction_proof.py"


def trusted_portable_measurement(
    *,
    platform: str,
    assertions: tuple[str, ...],
) -> Measurement:
    return Measurement(
        assertions=assertions,
        argv=("python", "reproduce.py", "--trust-embedded-predicate"),
        kind="portable-reproduction",
        platform=platform,
    )


def _digest_reference(value: object, *, label: str, allow_empty: bool = True) -> None:
    if not isinstance(value, dict) or set(value) != {"bytes", "sha256"}:
        raise ValueError(f"{label} must contain bytes and sha256")
    byte_count = value.get("bytes")
    digest = value.get("sha256")
    if (
        isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or byte_count < (0 if allow_empty else 1)
        or byte_count > 65_536
        or not isinstance(digest, str)
        or SHA256.fullmatch(digest) is None
    ):
        raise ValueError(f"{label} is invalid")


def validate_portable_proof(
    proof: object,
    *,
    expected_os: str,
    expected_commit: str,
) -> set[str]:
    if not isinstance(proof, dict):
        raise ValueError("portable proof must be an object")
    required = {
        "command",
        "commit",
        "collector",
        "export",
        "fresh_temporary_directory",
        "gate",
        "provider_keys_present",
        "runner",
        "schema_version",
        "source_tree_present",
    }
    if set(proof) != required:
        raise ValueError("portable proof fields are incomplete")
    if (
        expected_os not in PLATFORMS
        or GIT_SHA.fullmatch(expected_commit) is None
        or proof.get("schema_version") != 1
        or proof.get("gate") != "RS-G10"
        or proof.get("commit") != expected_commit
        or proof.get("fresh_temporary_directory") is not True
        or proof.get("source_tree_present") is not False
        or proof.get("provider_keys_present") != []
    ):
        raise ValueError("portable proof identity or isolation is invalid")
    runner = proof.get("runner")
    if (
        not isinstance(runner, dict)
        or set(runner) != {"arch", "os"}
        or runner.get("os") != expected_os
        or not isinstance(runner.get("arch"), str)
        or not 1 <= len(runner["arch"]) <= 64
    ):
        raise ValueError("portable proof runner metadata is invalid")
    collector = proof.get("collector")
    if (
        not isinstance(collector, dict)
        or set(collector) != {"path", "sha256"}
        or collector.get("path") != COLLECTOR_PATH
        or not isinstance(collector.get("sha256"), str)
        or SHA256.fullmatch(collector["sha256"]) is None
    ):
        raise ValueError("portable proof collector identity is invalid")
    command = proof.get("command")
    if not isinstance(command, dict) or set(command) != {
        "argv",
        "exit_code",
        "output_limit_bytes",
        "stderr",
        "stdout",
    }:
        raise ValueError("portable proof command fields are invalid")
    output_limit = command.get("output_limit_bytes")
    if (
        command.get("argv") != ["python", "reproduce.py", "--trust-embedded-predicate"]
        or command.get("exit_code") != 0
        or isinstance(output_limit, bool)
        or not isinstance(output_limit, int)
        or not 256 <= output_limit <= 65_536
    ):
        raise ValueError("portable proof command did not pass exactly one reproduction")
    _digest_reference(command.get("stdout"), label="portable stdout", allow_empty=False)
    _digest_reference(command.get("stderr"), label="portable stderr")
    if command["stdout"]["bytes"] + command["stderr"]["bytes"] > output_limit:
        raise ValueError("portable proof output exceeded its bound")
    export = proof.get("export")
    if (
        not isinstance(export, dict)
        or set(export) != {"capsule_sha256", "reproducer_sha256"}
        or any(
            not isinstance(export.get(name), str)
            or SHA256.fullmatch(export[name]) is None
            for name in ("capsule_sha256", "reproducer_sha256")
        )
    ):
        raise ValueError("portable proof export identity is invalid")
    return {
        "fresh-temp-run",
        f"{expected_os}-one-command",
        "no-api-key",
        "no-source-repository",
    }


def _read_bundle_file(base: Path, platform: str, name: str) -> bytes:
    path = base / f"portable-{platform}" / name
    try:
        path.resolve(strict=True).relative_to(base.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise ValueError(f"{platform} portable proof file is missing") from error
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{platform} portable proof file is not regular")
    return path.read_bytes()


def _validate_rs_g10(
    manifest: dict[str, Any],
    _proof: dict[str, Any],
    base: Path,
) -> set[str]:
    commit = manifest["commit"]
    collector = ROOT / COLLECTOR_PATH
    collector_bytes = collector.read_bytes()
    collector_sha256 = hashlib.sha256(collector_bytes).hexdigest()
    committed = subprocess.run(
        ["git", "show", f"{commit}:{COLLECTOR_PATH}"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if (
        committed.returncode
        or hashlib.sha256(committed.stdout).hexdigest() != collector_sha256
    ):
        raise ValueError("portable proof collector is not tied to the evidence commit")
    measured: set[str] = set()
    for platform in PLATFORMS:
        try:
            portable = json.loads(
                _read_bundle_file(base, platform, "proof.json").decode("utf-8")
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"{platform} portable proof JSON is invalid") from error
        measured.update(
            validate_portable_proof(
                portable,
                expected_os=platform,
                expected_commit=commit,
            )
        )
        if portable["collector"]["sha256"] != collector_sha256:
            raise ValueError(f"{platform} portable collector identity mismatch")
        command = portable["command"]
        for stream in ("stdout", "stderr"):
            data = _read_bundle_file(base, platform, f"command.{stream}")
            reference = command[stream]
            if (
                len(data) != reference["bytes"]
                or hashlib.sha256(data).hexdigest() != reference["sha256"]
            ):
                raise ValueError(f"{platform} portable {stream} does not match proof")
        export = portable["export"]
        if hashlib.sha256(
            _read_bundle_file(base, platform, "capsule.reprosieve")
        ).hexdigest() != export["capsule_sha256"]:
            raise ValueError(f"{platform} portable capsule identity mismatch")
        if hashlib.sha256(
            _read_bundle_file(base, platform, "reproduce.py")
        ).hexdigest() != export["reproducer_sha256"]:
            raise ValueError(f"{platform} portable reproducer identity mismatch")
    return measured


SPEC = GateSpec(
    gate="RS-G10",
    measurements=(
        trusted_portable_measurement(
            platform="linux",
            assertions=(
                "fresh-temp-run",
                "linux-one-command",
                "no-source-repository",
                "no-api-key",
            ),
        ),
        trusted_portable_measurement(
            platform="macos",
            assertions=("macos-one-command",),
        ),
    ),
    expected_support_sha256="c61b33ff9852dcde50c1204e083426b3b52e17fb922a4b7b8317c0f16a7c698d",
    extra_validator=_validate_rs_g10,
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
