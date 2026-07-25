from scripts.gates._verify import verify_gate

_SUPPORT = "2ed3d8ca8f51d6d8790a39abba8588110273229997156ac258d70abb62be53b9"

if __name__ == "__main__":
    raise SystemExit(
        verify_gate(
            gate="RS-G13",
            assertions=(
                "clean-install-py311",
                "clean-install-py312",
                "clean-install-py313",
                "wheel-sdist-smoke",
                "cli-smoke",
            ),
            pytest_nodes=(
                "tests/test_release_contract.py::test_ci_declares_supported_python_and_portable_reproduction_matrix",
                "tests/test_release_contract.py::test_cli_help_starts_without_the_optional_sdk_imported",
            ),
            expected_support_sha256=_SUPPORT,
        )
    )
