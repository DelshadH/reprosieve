from scripts.gates._verify import verify_gate

_SUPPORT = "2ed3d8ca8f51d6d8790a39abba8588110273229997156ac258d70abb62be53b9"

if __name__ == "__main__":
    raise SystemExit(
        verify_gate(
            gate="RS-G09",
            assertions=(
                "k-of-n-bookkeeping",
                "fresh-trial-isolation",
                "cache-key-complete",
                "attempt-report-complete",
                "probabilistic-label",
            ),
            pytest_nodes=(
                "tests/test_predicate.py::test_each_probabilistic_trial_is_fresh_and_all_attempts_are_recorded",
                "tests/test_predicate.py::test_predicate_output_is_hashed_not_retained_and_cache_key_is_complete",
            ),
            expected_support_sha256=_SUPPORT,
        )
    )
