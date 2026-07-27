from pathlib import Path
from typing import Any

from scripts.gates._verify import (
    GateSpec,
    pytest_measurement,
    require_pytest_pass,
    verify_gate,
)


def _validate_rs_g03(
    manifest: dict[str, Any],
    _proof: dict[str, Any],
    base: Path,
) -> set[str]:
    assertions: set[str] = set()
    for index, assertion in enumerate(
        (
            "capsule-hash-repeatable",
            "member-hashes-verified",
            "traversal-rejected",
            "archive-bomb-rejected",
            "malformed-reference-rejected",
        )
    ):
        require_pytest_pass(manifest, base, index)
        assertions.add(assertion)
    return assertions


SPEC = GateSpec(
    gate="RS-G03",
    measurements=(
        pytest_measurement(
            ("capsule-hash-repeatable",),
            "tests/test_capsule.py::test_capsule_is_deterministic_validated_and_immutable",
        ),
        pytest_measurement(
            ("member-hashes-verified",),
            "tests/test_capsule.py::test_manifest_covers_every_payload_and_corruption_is_rejected",
        ),
        pytest_measurement(
            ("traversal-rejected",),
            "tests/test_capsule.py::test_archive_traversal_is_rejected",
        ),
        pytest_measurement(
            ("archive-bomb-rejected",),
            "tests/test_capsule.py::test_duplicate_symlink_bomb_and_oversize_archives_are_rejected",
        ),
        pytest_measurement(
            ("malformed-reference-rejected",),
            "tests/test_schema.py::SchemaTests::test_missing_dependency_is_rejected",
        ),
    ),
    expected_support_sha256="9367e4e2453ac18c465b11ac35fb31ac45df71383d6e84b7bf3b184b58c7a21d",
    extra_validator=_validate_rs_g03,
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
