import json
from pathlib import Path
from typing import Any

from scripts.gates._verify import (
    GateSpec,
    Measurement,
    _safe_blob,
    pytest_measurement,
    require_pytest_pass,
    verify_gate,
)
from scripts.minimality_oracle_proof import validate_oracle_document


def _validate_rs_g06(
    manifest: dict[str, Any],
    _proof: dict[str, Any],
    base: Path,
) -> set[str]:
    command = manifest["commands"][0]
    _path, stdout = _safe_blob(
        base,
        command["stdout"],
        label="minimality oracle stdout",
    )
    try:
        oracle = json.loads(stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("minimality oracle output is invalid JSON") from error
    validate_oracle_document(oracle)
    require_pytest_pass(manifest, base, 1)
    return {
        "every-unit-removal-checked",
        "no-removable-reproducer",
        "invalid-reasons-recorded",
    }


SPEC = GateSpec(
    gate="RS-G06",
    measurements=(
        Measurement(
            assertions=("every-unit-removal-checked", "no-removable-reproducer"),
            argv=("python", "-m", "scripts.minimality_oracle_proof"),
            kind="minimality-oracle",
        ),
        pytest_measurement(
            ("invalid-reasons-recorded",),
            "tests/test_hierarchy.py::test_minimality_proof_records_predicate_invalid_reasons",
        ),
    ),
    expected_support_sha256="9367e4e2453ac18c465b11ac35fb31ac45df71383d6e84b7bf3b184b58c7a21d",
    extra_validator=_validate_rs_g06,
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
