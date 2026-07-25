from scripts.gates._verify import GateSpec, pytest_measurement, verify_gate

SPEC = GateSpec(
    gate="RS-G09",
    measurements=(
        pytest_measurement(
            (
                "k-of-n-bookkeeping",
                "fresh-trial-isolation",
                "cache-key-complete",
                "attempt-report-complete",
                "probabilistic-label",
            ),
            "tests/test_predicate.py::test_each_probabilistic_trial_is_fresh_and_all_attempts_are_recorded",
            "tests/test_predicate.py::test_predicate_output_is_hashed_not_retained_and_cache_key_is_complete",
        ),
    ),
    expected_support_sha256="0487c43e903dbd2621b94e982dd02c2ad77b319311ad6401c4fcfee9b7a7fc90",
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
