from scripts.gates._verify import GateSpec, pytest_measurement, verify_gate

SPEC = GateSpec(
    gate="RS-G03",
    measurements=(
        pytest_measurement(
            (
                "capsule-hash-repeatable",
                "member-hashes-verified",
                "traversal-rejected",
                "archive-bomb-rejected",
                "malformed-reference-rejected",
            ),
            "tests/test_capsule.py",
            "tests/test_schema.py",
        ),
    ),
    expected_support_sha256="0487c43e903dbd2621b94e982dd02c2ad77b319311ad6401c4fcfee9b7a7fc90",
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
