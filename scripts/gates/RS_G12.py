from scripts.gates._verify import GateSpec, pytest_measurement, verify_gate

SPEC = GateSpec(
    gate="RS-G12",
    measurements=(
        pytest_measurement(
            (
                "clean-checkout",
                "full-tests",
                "killer-minimize",
                "repro-export",
                "minimality-verify",
                "terminal-demo-duration",
            ),
            "tests/test_release_contract.py::test_killer_demo_completes_the_full_claim_within_twenty_seconds",
            "tests/test_cli_e2e.py::test_minimize_verify_replay_and_one_command_export",
            "tests/test_hierarchy.py::test_real_247_event_fixture_reduces_to_at_most_ten_and_is_one_minimal",
        ),
    ),
    expected_support_sha256="0487c43e903dbd2621b94e982dd02c2ad77b319311ad6401c4fcfee9b7a7fc90",
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
