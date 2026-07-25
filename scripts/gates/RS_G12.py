from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from scripts.gates._verify import GateSpec, Measurement, _safe_blob, verify_gate

_TESTS = re.compile(rb"\b\d+ passed(?:, \d+ subtests passed)?\b")
_REDUCTION = re.compile(rb"\breduced 247 events to (\d+); 1-minimal\b")
_DURATION = re.compile(rb"\bkiller demo passed in ([0-9]+(?:\.[0-9]+)?)s\b")


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
    return validate_release_outputs(verification, demo)


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
