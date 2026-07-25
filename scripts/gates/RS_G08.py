from scripts.gates._verify import GateSpec, pytest_measurement, verify_gate

SPEC = GateSpec(
    gate="RS-G08",
    measurements=(
        pytest_measurement(
            (
                "span-reduction",
                "message-reduction",
                "tool-pair-reduction",
                "json-field-reduction",
                "text-reduction",
                "file-reduction",
                "environment-reduction",
            ),
            "tests/test_hierarchy.py::test_each_hierarchy_level_accepts_a_real_reduction",
        ),
    ),
    expected_support_sha256="0487c43e903dbd2621b94e982dd02c2ad77b319311ad6401c4fcfee9b7a7fc90",
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
