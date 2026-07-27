from pathlib import Path
from typing import Any

from scripts.gates._verify import (
    GateSpec,
    pytest_measurement,
    require_pytest_pass,
    verify_gate,
)


def _validate_rs_g04(
    manifest: dict[str, Any],
    _proof: dict[str, Any],
    base: Path,
) -> set[str]:
    assertions: set[str] = set()
    for index, assertion in enumerate(
        (
            "provider-key-absent",
            "network-denied",
            "recorded-values-materialized",
            "predicate-only-executed",
            "provider-call-canary-untouched",
            "original-tool-canary-untouched",
            "target-failure-reproduced",
        )
    ):
        require_pytest_pass(manifest, base, index)
        assertions.add(assertion)
    return assertions


SPEC = GateSpec(
    gate="RS-G04",
    measurements=(
        pytest_measurement(
            ("provider-key-absent",),
            "tests/test_predicate.py::test_offline_guard_removes_provider_keys_proxies_and_network",
        ),
        pytest_measurement(
            ("network-denied",),
            "tests/test_predicate.py::test_offline_guard_rejects_socket_audit_events_without_opening_a_connection",
        ),
        pytest_measurement(
            ("recorded-values-materialized",),
            "tests/test_replay.py::test_offline_replay_substitutes_recorded_model_and_tool_outputs",
        ),
        pytest_measurement(
            ("predicate-only-executed",),
            "tests/test_predicate.py::test_predicate_reproduction_executes_only_the_declared_workspace_entrypoint",
        ),
        pytest_measurement(
            ("provider-call-canary-untouched",),
            "tests/test_replay.py::test_materialization_leaves_provider_import_canary_untouched",
        ),
        pytest_measurement(
            ("original-tool-canary-untouched",),
            "tests/test_replay.py::test_materialization_leaves_original_tool_entrypoint_canary_untouched",
        ),
        pytest_measurement(
            ("target-failure-reproduced",),
            "tests/test_cli_e2e.py::test_reproduce_predicate_runs_the_declared_offline_predicate",
        ),
    ),
    expected_support_sha256="9367e4e2453ac18c465b11ac35fb31ac45df71383d6e84b7bf3b184b58c7a21d",
    extra_validator=_validate_rs_g04,
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
