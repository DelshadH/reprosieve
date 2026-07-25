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
            "model-not-called",
            "external-tools-not-called",
            "failure-reproduced",
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
            ("model-not-called",),
            "tests/test_replay.py::test_offline_replay_substitutes_recorded_model_and_tool_outputs",
        ),
        pytest_measurement(
            ("external-tools-not-called",),
            "tests/test_replay.py::test_offline_replay_substitutes_recorded_model_and_tool_outputs",
        ),
        pytest_measurement(
            ("failure-reproduced",),
            "tests/test_cli_e2e.py::test_reproduce_predicate_runs_the_declared_offline_predicate",
        ),
    ),
    expected_support_sha256="c61b33ff9852dcde50c1204e083426b3b52e17fb922a4b7b8317c0f16a7c698d",
    extra_validator=_validate_rs_g04,
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
