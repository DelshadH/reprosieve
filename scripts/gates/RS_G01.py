from scripts.gates._verify import GateSpec, pytest_measurement, verify_gate

SPEC = GateSpec(
    gate="RS-G01",
    measurements=(
        pytest_measurement(
            (
                "public-processor-only",
                "default-exporter-replaced",
                "no-duplicate-export",
                "sdk-private-import-scan",
                "synthetic-trace-captured",
            ),
            "tests/test_openai_adapter.py",
        ),
    ),
    expected_support_sha256="0487c43e903dbd2621b94e982dd02c2ad77b319311ad6401c4fcfee9b7a7fc90",
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
