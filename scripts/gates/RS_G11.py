from scripts.gates._verify import GateSpec, pytest_measurement, verify_gate

SPEC = GateSpec(
    gate="RS-G11",
    measurements=(
        pytest_measurement(
            (
                "timeout-bound",
                "output-cap",
                "event-cap",
                "archive-cap",
                "recursion-cap",
                "cancellation",
            ),
            "tests/test_schema.py",
            "tests/test_capsule.py::test_duplicate_symlink_bomb_and_oversize_archives_are_rejected",
            "tests/test_redact.py::RedactionTests::test_bounded_traversal_rejects_deep_or_huge_payloads_without_echo",
            "tests/test_redact.py::RedactionTests::test_rejects_regex_forms_that_cannot_be_bounded",
            "tests/test_predicate.py::test_timeout_output_limit_and_signal_are_invalid",
            "tests/test_predicate.py::test_cancellation_stops_a_running_predicate",
        ),
    ),
    expected_support_sha256="0487c43e903dbd2621b94e982dd02c2ad77b319311ad6401c4fcfee9b7a7fc90",
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
