from scripts.gates._verify import GateSpec, pytest_measurement, verify_gate

SPEC = GateSpec(
    gate="RS-G07",
    measurements=(
        pytest_measurement(
            (
                "reproduces-distinct",
                "absent-distinct",
                "invalid-distinct",
                "timeout-invalid",
                "signal-invalid",
            ),
            "tests/test_predicate.py::test_exit_protocol_is_strict",
            "tests/test_predicate.py::test_timeout_output_limit_and_signal_are_invalid",
            "tests/test_hierarchy.py::test_invalid_candidates_are_never_accepted",
        ),
    ),
    expected_support_sha256="0487c43e903dbd2621b94e982dd02c2ad77b319311ad6401c4fcfee9b7a7fc90",
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
