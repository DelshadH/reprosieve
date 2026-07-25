from scripts.gates._verify import verify_gate

_SUPPORT = "2ed3d8ca8f51d6d8790a39abba8588110273229997156ac258d70abb62be53b9"

if __name__ == "__main__":
    raise SystemExit(
        verify_gate(
            gate="RS-G11",
            assertions=(
                "timeout-bound",
                "output-cap",
                "event-cap",
                "archive-cap",
                "recursion-cap",
                "cancellation",
            ),
            pytest_nodes=(
                "tests/test_schema.py",
                "tests/test_capsule.py::test_duplicate_symlink_bomb_and_oversize_archives_are_rejected",
                "tests/test_redact.py::RedactionTests::test_bounded_traversal_rejects_deep_or_huge_payloads_without_echo",
                "tests/test_redact.py::RedactionTests::test_rejects_regex_forms_that_cannot_be_bounded",
                "tests/test_predicate.py::test_timeout_output_limit_and_signal_are_invalid",
                "tests/test_predicate.py::test_cancellation_stops_a_running_predicate",
            ),
            expected_support_sha256=_SUPPORT,
        )
    )
