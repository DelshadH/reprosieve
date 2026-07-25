from scripts.gates._verify import verify_gate

_SUPPORT = "2ed3d8ca8f51d6d8790a39abba8588110273229997156ac258d70abb62be53b9"

if __name__ == "__main__":
    raise SystemExit(
        verify_gate(
            gate="RS-G10",
            assertions=(
                "fresh-temp-run",
                "linux-one-command",
                "macos-one-command",
                "no-source-repository",
                "no-api-key",
            ),
            pytest_nodes=(
                "tests/test_release_contract.py::test_ci_declares_supported_python_and_portable_reproduction_matrix",
                "tests/test_cli_e2e.py::test_minimize_verify_replay_and_one_command_export",
                "tests/test_export_security.py::test_standalone_reproducer_restores_declared_environment",
            ),
            expected_support_sha256=_SUPPORT,
        )
    )
