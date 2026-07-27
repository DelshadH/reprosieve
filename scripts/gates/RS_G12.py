from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

from scripts.gates._verify import GateSpec, Measurement, _safe_blob, verify_gate

_TESTS = re.compile(rb"\b\d+ passed(?:, \d+ subtests passed)?\b")
_REDUCTION = re.compile(rb"\breduced 247 events to (\d+); 1-minimal\b")
_DURATION = re.compile(rb"\bkiller demo passed in ([0-9]+(?:\.[0-9]+)?)s\b")
ROOT = Path(__file__).resolve().parents[2]


def _repository_file(root: Path, base: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{label}: invalid repository path")
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError(f"{label}: invalid repository path")
    target = base.joinpath(*relative.parts).resolve(strict=True)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label}: path escapes repository") from exc
    if not target.is_file():
        raise ValueError(f"{label}: path is not a file")
    return target


def assert_evidence_files_tracked(*, root: Path, gate: str, manifest_path: Path, manifest: dict[str, Any]) -> None:
    root_real = root.resolve(strict=True)
    base = manifest_path.parent
    targets = [manifest_path.resolve(strict=True)]
    for index, command in enumerate(manifest["commands"]):
        targets.append(_repository_file(root_real, base, command["stdout"]["path"], f"{gate}.commands[{index}].stdout"))
        targets.append(_repository_file(root_real, base, command["stderr"]["path"], f"{gate}.commands[{index}].stderr"))
    for index, artifact in enumerate(manifest["artifacts"]):
        targets.append(_repository_file(root_real, base, artifact["path"], f"{gate}.artifacts[{index}]"))
    targets.append(_repository_file(root_real, root_real, manifest["verifier"]["path"], f"{gate}.verifier"))

    for target in dict.fromkeys(targets):
        relative = target.relative_to(root_real).as_posix()
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relative],
            cwd=root_real,
            capture_output=True,
            text=True,
            check=False,
        )
        committed = subprocess.run(
            ["git", "cat-file", "-e", f"HEAD:{relative}"],
            cwd=root_real,
            capture_output=True,
            text=True,
            check=False,
        )
        if tracked.returncode or committed.returncode:
            raise ValueError(f"{gate}: evidence file is not Git-tracked in HEAD: {relative}")


def assert_release_evidence_tracked(root: Path = ROOT) -> None:
    try:
        progress = json.loads((root / "PROGRESS.json").read_text(encoding="utf-8"))
        gates = progress["gates"]
    except (KeyError, OSError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("RS-G12: cannot load release evidence registry") from exc
    seen: set[str] = set()
    for gate, state in gates.items():
        for reference in state["evidence"]:
            path_value = reference["path"]
            if path_value in seen:
                continue
            seen.add(path_value)
            manifest_path = _repository_file(root.resolve(strict=True), root, path_value, f"{gate}.manifest")
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"{gate}: cannot load evidence manifest") from exc
            assert_evidence_files_tracked(
                root=root,
                gate=gate,
                manifest_path=manifest_path,
                manifest=manifest,
            )


def validate_release_outputs(verification: bytes, demo: bytes) -> set[str]:
    if (
        b"RunSieve contract-v2 self-tests passed" not in verification
        or _TESTS.search(verification) is None
        or b"All checks passed!" not in verification
        or b"Success: no issues found" not in verification
    ):
        raise ValueError("RS-G12 full verification output is incomplete")
    reduction = _REDUCTION.search(demo)
    duration = _DURATION.search(demo)
    if (
        reduction is None
        or int(reduction.group(1)) > 10
        or b"wrote deterministic recorded-output materialization" not in demo
        or b'"result":"reproduces"' not in demo
        or b"exported one-command offline issue reproduction" not in demo
        or duration is None
        or float(duration.group(1)) > 20
    ):
        raise ValueError("RS-G12 killer-demo output does not prove the release claim")
    return {
        "clean-checkout",
        "full-tests",
        "killer-reduce",
        "recorded-values-materialize",
        "predicate-reproduce",
        "repro-export",
        "minimality-verify",
        "terminal-demo-duration",
    }


def _validate_rs_g12(
    manifest: dict[str, Any],
    _proof: dict[str, Any],
    base: Path,
) -> set[str]:
    commands = manifest["commands"]
    if not isinstance(commands, list) or len(commands) != 2:
        raise ValueError("RS-G12 requires full-verification and demo commands")
    _verification_path, verification = _safe_blob(
        base,
        commands[0]["stdout"],
        label="RS-G12 verification stdout",
    )
    _demo_path, demo = _safe_blob(
        base,
        commands[1]["stdout"],
        label="RS-G12 demo stdout",
    )
    assertions = validate_release_outputs(verification, demo)
    assert_release_evidence_tracked()
    return assertions


SPEC = GateSpec(
    gate="RS-G12",
    measurements=(
        Measurement(
            assertions=("clean-checkout", "full-tests"),
            argv=("python", "-m", "scripts.verify"),
            kind="command",
        ),
        Measurement(
            assertions=(
                "killer-reduce",
                "recorded-values-materialize",
                "predicate-reproduce",
                "repro-export",
                "minimality-verify",
                "terminal-demo-duration",
            ),
            argv=("python", "scripts/killer_demo.py"),
            kind="command",
        ),
    ),
    expected_support_sha256="c61b33ff9852dcde50c1204e083426b3b52e17fb922a4b7b8317c0f16a7c698d",
    extra_validator=_validate_rs_g12,
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
