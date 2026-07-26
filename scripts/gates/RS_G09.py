from pathlib import Path
from typing import Any

from scripts.gates._verify import (
    GateSpec,
    pytest_measurement,
    require_pytest_pass,
    verify_gate,
)

_TRIAL_TEST = (
    "tests/test_predicate.py::"
    "test_each_probabilistic_trial_is_fresh_and_all_attempts_are_recorded"
)


def _validate_rs_g09(
    manifest: dict[str, Any],
    _proof: dict[str, Any],
    base: Path,
) -> set[str]:
    assertions: set[str] = set()
    for index, assertion in enumerate(
        (
            "k-of-n-predicate-bookkeeping",
            "fresh-trial-isolation",
            "cache-key-complete",
            "attempt-report-complete",
            "probabilistic-predicate-label",
        )
    ):
        require_pytest_pass(manifest, base, index)
        assertions.add(assertion)
    return assertions


SPEC = GateSpec(
    gate="RS-G09",
    measurements=(
        pytest_measurement(("k-of-n-predicate-bookkeeping",), _TRIAL_TEST),
        pytest_measurement(("fresh-trial-isolation",), _TRIAL_TEST),
        pytest_measurement(
            ("cache-key-complete",),
            "tests/test_predicate.py::test_predicate_output_is_hashed_not_retained_and_cache_key_is_complete",
        ),
        pytest_measurement(("attempt-report-complete",), _TRIAL_TEST),
        pytest_measurement(("probabilistic-predicate-label",), _TRIAL_TEST),
    ),
    expected_support_sha256="c61b33ff9852dcde50c1204e083426b3b52e17fb922a4b7b8317c0f16a7c698d",
    extra_validator=_validate_rs_g09,
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
