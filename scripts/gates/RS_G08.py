from pathlib import Path
from typing import Any

from scripts.gates._verify import (
    GateSpec,
    pytest_measurement,
    require_pytest_pass,
    verify_gate,
)

_HIERARCHY_TEST = (
    "tests/test_hierarchy.py::test_each_hierarchy_level_accepts_a_real_reduction"
)
_ASSERTIONS = (
    "span-reduction",
    "message-reduction",
    "tool-pair-reduction",
    "json-field-reduction",
    "text-reduction",
    "file-reduction",
    "environment-reduction",
)


def _validate_rs_g08(
    manifest: dict[str, Any],
    _proof: dict[str, Any],
    base: Path,
) -> set[str]:
    assertions: set[str] = set()
    for index, assertion in enumerate(_ASSERTIONS):
        require_pytest_pass(manifest, base, index)
        assertions.add(assertion)
    return assertions


SPEC = GateSpec(
    gate="RS-G08",
    measurements=tuple(
        pytest_measurement((assertion,), _HIERARCHY_TEST)
        for assertion in _ASSERTIONS
    ),
    expected_support_sha256="c61b33ff9852dcde50c1204e083426b3b52e17fb922a4b7b8317c0f16a7c698d",
    extra_validator=_validate_rs_g08,
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
