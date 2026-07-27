from pathlib import Path
from typing import Any

from scripts.gates._verify import (
    GateSpec,
    pytest_measurement,
    require_pytest_pass,
    verify_gate,
)

_FIXTURE_TEST = (
    "tests/test_hierarchy.py::"
    "test_real_247_event_fixture_reduces_to_at_most_ten_and_is_one_minimal"
)


def _validate_rs_g05(
    manifest: dict[str, Any],
    _proof: dict[str, Any],
    base: Path,
) -> set[str]:
    assertions: set[str] = set()
    for index, assertion in enumerate(
        (
            "source-events-247",
            "reduced-events-max-10",
            "predicate-preserved",
            "referential-integrity",
        )
    ):
        require_pytest_pass(manifest, base, index)
        assertions.add(assertion)
    return assertions


SPEC = GateSpec(
    gate="RS-G05",
    measurements=tuple(
        pytest_measurement((assertion,), _FIXTURE_TEST)
        for assertion in (
            "source-events-247",
            "reduced-events-max-10",
            "predicate-preserved",
            "referential-integrity",
        )
    ),
    expected_support_sha256="c61b33ff9852dcde50c1204e083426b3b52e17fb922a4b7b8317c0f16a7c698d",
    extra_validator=_validate_rs_g05,
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
