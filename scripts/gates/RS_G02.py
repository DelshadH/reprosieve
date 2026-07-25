from scripts.gates._verify import verify_gate

_SUPPORT = "2ed3d8ca8f51d6d8790a39abba8588110273229997156ac258d70abb62be53b9"

if __name__ == "__main__":
    raise SystemExit(
        verify_gate(
            gate="RS-G02",
            assertions=(
                "files-canary-free",
                "archives-canary-free",
                "stdio-canary-free",
                "exceptions-canary-free",
                "redaction-before-write",
            ),
            pytest_nodes=(
                "tests/test_redact.py",
                "tests/test_capsule.py::test_canary_never_reaches_capsule_bytes_or_errors",
                "tests/test_cli_e2e.py::test_capture_runs_real_sdk_target_and_redacts_process_output",
            ),
            expected_support_sha256=_SUPPORT,
        )
    )
