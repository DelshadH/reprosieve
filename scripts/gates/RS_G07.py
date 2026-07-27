from pathlib import Path
from typing import Any

from scripts.gates._verify import (
    GateSpec,
    pytest_measurement,
    require_pytest_pass,
    verify_gate,
)

_EXIT_TEST = "tests/test_predicate.py::test_exit_protocol_is_strict"
_LIMIT_TEST = "tests/test_predicate.py::test_timeout_output_limit_and_signal_are_invalid"


def _validate_rs_g07(
    manifest: dict[str, Any],
    _proof: dict[str, Any],
    base: Path,
) -> set[str]:
    assertions: set[str] = set()
    for index, assertion in enumerate(
        (
            "reproduces-distinct",
            "absent-distinct",
            "invalid-distinct",
            "timeout-invalid",
            "signal-invalid",
        )
    ):
        require_pytest_pass(manifest, base, index)
        assertions.add(assertion)
    return assertions


SPEC = GateSpec(
    gate="RS-G07",
    measurements=(
        pytest_measurement(("reproduces-distinct",), _EXIT_TEST),
        pytest_measurement(("absent-distinct",), _EXIT_TEST),
        pytest_measurement(("invalid-distinct",), _EXIT_TEST),
        pytest_measurement(("timeout-invalid",), _LIMIT_TEST),
        pytest_measurement(("signal-invalid",), _LIMIT_TEST),
    ),
    expected_support_sha256="9367e4e2453ac18c465b11ac35fb31ac45df71383d6e84b7bf3b184b58c7a21d",
    extra_validator=_validate_rs_g07,
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
