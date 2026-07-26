from pathlib import Path
from typing import Any

from scripts.gates._verify import (
    GateSpec,
    pytest_measurement,
    require_pytest_pass,
    verify_gate,
)

_MINIMAL_TEST = (
    "tests/test_hierarchy.py::"
    "test_real_247_event_fixture_reduces_to_at_most_ten_and_is_one_minimal"
)


def _validate_rs_g06(
    manifest: dict[str, Any],
    _proof: dict[str, Any],
    base: Path,
) -> set[str]:
    assertions: set[str] = set()
    for index, assertion in enumerate(
        (
            "every-unit-removal-checked",
            "no-removable-reproducer",
            "invalid-reasons-recorded",
        )
    ):
        require_pytest_pass(manifest, base, index)
        assertions.add(assertion)
    return assertions


SPEC = GateSpec(
    gate="RS-G06",
    measurements=(
        pytest_measurement(("every-unit-removal-checked",), _MINIMAL_TEST),
        pytest_measurement(("no-removable-reproducer",), _MINIMAL_TEST),
        pytest_measurement(
            ("invalid-reasons-recorded",),
            "tests/test_hierarchy.py::test_minimality_proof_records_predicate_invalid_reasons",
        ),
    ),
    expected_support_sha256="c61b33ff9852dcde50c1204e083426b3b52e17fb922a4b7b8317c0f16a7c698d",
    extra_validator=_validate_rs_g06,
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
