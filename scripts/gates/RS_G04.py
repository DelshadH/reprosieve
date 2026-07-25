from scripts.gates._verify import verify_gate

_SUPPORT = "2ed3d8ca8f51d6d8790a39abba8588110273229997156ac258d70abb62be53b9"

if __name__ == "__main__":
    raise SystemExit(
        verify_gate(
            gate="RS-G04",
            assertions=(
                "provider-key-absent",
                "network-denied",
                "model-not-called",
                "external-tools-not-called",
                "failure-reproduced",
            ),
            pytest_nodes=(
                "tests/test_replay.py",
                "tests/test_predicate.py::test_offline_guard_removes_provider_keys_proxies_and_network",
                "tests/test_predicate.py::test_offline_guard_rejects_socket_audit_events_without_opening_a_connection",
                "tests/test_export_security.py::test_standalone_reproducer_denies_network_audit_event_without_connection",
            ),
            expected_support_sha256=_SUPPORT,
        )
    )
