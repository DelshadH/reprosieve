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
    expected_support_sha256="9367e4e2453ac18c465b11ac35fb31ac45df71383d6e84b7bf3b184b58c7a21d",
    extra_validator=_validate_rs_g09,
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
