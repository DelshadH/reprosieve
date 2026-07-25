from scripts.gates._verify import GateSpec, pytest_measurement, verify_gate

SPEC = GateSpec(
    gate="RS-G05",
    measurements=(
        pytest_measurement(
            (
                "source-events-247",
                "reduced-events-max-10",
                "predicate-preserved",
                "referential-integrity",
            ),
            "tests/test_hierarchy.py::test_real_247_event_fixture_reduces_to_at_most_ten_and_is_one_minimal",
        ),
    ),
    expected_support_sha256="0487c43e903dbd2621b94e982dd02c2ad77b319311ad6401c4fcfee9b7a7fc90",
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
