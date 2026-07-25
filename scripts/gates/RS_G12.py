from scripts.gates._verify import verify_gate

_SUPPORT = "2ed3d8ca8f51d6d8790a39abba8588110273229997156ac258d70abb62be53b9"

if __name__ == "__main__":
    raise SystemExit(
        verify_gate(
            gate="RS-G12",
            assertions=(
                "clean-checkout",
                "full-tests",
                "killer-minimize",
                "repro-export",
                "minimality-verify",
                "terminal-demo-duration",
            ),
            pytest_nodes=(
                "tests/test_release_contract.py::test_killer_demo_completes_the_full_claim_within_twenty_seconds",
                "tests/test_cli_e2e.py::test_minimize_verify_replay_and_one_command_export",
                "tests/test_hierarchy.py::test_real_247_event_fixture_reduces_to_at_most_ten_and_is_one_minimal",
            ),
            expected_support_sha256=_SUPPORT,
        )
    )
