from pathlib import Path
from typing import Any

from scripts.gates._verify import (
    GateSpec,
    pytest_measurement,
    require_pytest_pass,
    verify_gate,
)

_LIMIT_TEST = "tests/test_predicate.py::test_timeout_output_limit_and_signal_are_invalid"


def _validate_rs_g11(
    manifest: dict[str, Any],
    _proof: dict[str, Any],
    base: Path,
) -> set[str]:
    assertions: set[str] = set()
    for index, assertion in enumerate(
        (
            "timeout-bound",
            "output-cap",
            "event-cap",
            "archive-cap",
            "recursion-cap",
            "cancellation",
        )
    ):
        require_pytest_pass(manifest, base, index)
        assertions.add(assertion)
    return assertions


SPEC = GateSpec(
    gate="RS-G11",
    measurements=(
        pytest_measurement(("timeout-bound",), _LIMIT_TEST),
        pytest_measurement(("output-cap",), _LIMIT_TEST),
        pytest_measurement(
            ("event-cap",),
            "tests/test_schema.py::SchemaTests::test_enforces_event_and_recursion_limits",
        ),
        pytest_measurement(
            ("archive-cap",),
            "tests/test_capsule.py::test_duplicate_symlink_bomb_and_oversize_archives_are_rejected",
        ),
        pytest_measurement(
            ("recursion-cap",),
            "tests/test_redact.py::RedactionTests::test_bounded_traversal_rejects_deep_or_huge_payloads_without_echo",
        ),
        pytest_measurement(
            ("cancellation",),
            "tests/test_predicate.py::test_cancellation_stops_a_running_predicate",
        ),
    ),
    expected_support_sha256="c61b33ff9852dcde50c1204e083426b3b52e17fb922a4b7b8317c0f16a7c698d",
    extra_validator=_validate_rs_g11,
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
