from pathlib import Path
from typing import Any

from scripts.gates._verify import (
    GateSpec,
    pytest_measurement,
    require_pytest_pass,
    verify_gate,
)


def _validate_rs_g02(
    manifest: dict[str, Any],
    _proof: dict[str, Any],
    base: Path,
) -> set[str]:
    assertions: set[str] = set()
    for index, assertion in enumerate(
        (
            "files-canary-free",
            "archives-canary-free",
            "stdio-canary-free",
            "exceptions-canary-free",
            "redaction-before-write",
        )
    ):
        require_pytest_pass(manifest, base, index)
        assertions.add(assertion)
    return assertions


SPEC = GateSpec(
    gate="RS-G02",
    measurements=(
        pytest_measurement(
            ("files-canary-free",),
            "tests/test_openai_adapter.py::test_declared_workspace_and_environment_are_bounded_redacted_and_sanitized",
        ),
        pytest_measurement(
            ("archives-canary-free",),
            "tests/test_capsule.py::test_canary_never_reaches_capsule_bytes_or_errors",
        ),
        pytest_measurement(
            ("stdio-canary-free",),
            "tests/test_cli_e2e.py::test_capture_runs_real_sdk_target_and_redacts_process_output",
        ),
        pytest_measurement(
            ("exceptions-canary-free",),
            "tests/test_capsule.py::test_canary_never_reaches_capsule_bytes_or_errors",
        ),
        pytest_measurement(
            ("redaction-before-write",),
            "tests/test_openai_adapter.py::test_declared_workspace_and_environment_are_bounded_redacted_and_sanitized",
        ),
    ),
    expected_support_sha256="c61b33ff9852dcde50c1204e083426b3b52e17fb922a4b7b8317c0f16a7c698d",
    extra_validator=_validate_rs_g02,
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
