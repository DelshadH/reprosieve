from scripts.gates._verify import verify_gate

_SUPPORT = "2ed3d8ca8f51d6d8790a39abba8588110273229997156ac258d70abb62be53b9"

if __name__ == "__main__":
    raise SystemExit(
        verify_gate(
            gate="RS-G06",
            assertions=(
                "every-unit-removal-checked",
                "no-removable-reproducer",
                "invalid-reasons-recorded",
            ),
            pytest_nodes=(
                "tests/test_hierarchy.py::test_real_247_event_fixture_reduces_to_at_most_ten_and_is_one_minimal",
            ),
            expected_support_sha256=_SUPPORT,
        )
    )
