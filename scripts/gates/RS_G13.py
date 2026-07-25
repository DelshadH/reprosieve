from scripts.gates._verify import GateSpec, pytest_measurement, verify_gate

SPEC = GateSpec(
    gate="RS-G13",
    measurements=(
        pytest_measurement(
            (
                "clean-install-py311",
                "clean-install-py312",
                "clean-install-py313",
                "wheel-sdist-smoke",
                "cli-smoke",
            ),
            "tests/test_release_contract.py::test_ci_declares_supported_python_and_portable_reproduction_matrix",
            "tests/test_release_contract.py::test_cli_help_starts_without_the_optional_sdk_imported",
        ),
    ),
    expected_support_sha256="0487c43e903dbd2621b94e982dd02c2ad77b319311ad6401c4fcfee9b7a7fc90",
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
