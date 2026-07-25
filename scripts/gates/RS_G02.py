from scripts.gates._verify import GateSpec, pytest_measurement, verify_gate

SPEC = GateSpec(
    gate="RS-G02",
    measurements=(
        pytest_measurement(
            (
                "files-canary-free",
                "archives-canary-free",
                "stdio-canary-free",
                "exceptions-canary-free",
                "redaction-before-write",
            ),
            "tests/test_redact.py",
            "tests/test_capsule.py::test_canary_never_reaches_capsule_bytes_or_errors",
            "tests/test_cli_e2e.py::test_capture_runs_real_sdk_target_and_redacts_process_output",
        ),
    ),
    expected_support_sha256="0487c43e903dbd2621b94e982dd02c2ad77b319311ad6401c4fcfee9b7a7fc90",
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
