from scripts.gates._verify import GateSpec, pytest_measurement, verify_gate

SPEC = GateSpec(
    gate="RS-G04",
    measurements=(
        pytest_measurement(
            (
                "provider-key-absent",
                "network-denied",
                "model-not-called",
                "external-tools-not-called",
                "failure-reproduced",
            ),
            "tests/test_replay.py",
            "tests/test_predicate.py::test_offline_guard_removes_provider_keys_proxies_and_network",
            "tests/test_predicate.py::test_offline_guard_rejects_socket_audit_events_without_opening_a_connection",
            "tests/test_export_security.py::test_standalone_reproducer_denies_network_audit_event_without_connection",
        ),
    ),
    expected_support_sha256="0487c43e903dbd2621b94e982dd02c2ad77b319311ad6401c4fcfee9b7a7fc90",
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
