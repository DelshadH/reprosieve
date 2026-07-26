from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, cast

from reprosieve.capsule import canonical_json
from reprosieve.safeio import ensure_real_directory, ensure_regular_file
from reprosieve.schema import safe_relative_path

_CASE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_MAX_MANIFEST_BYTES = 1024 * 1024
_MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
_MAX_TOTAL_BYTES = 64 * 1024 * 1024
_CATEGORIES = {
    "application-model-trajectory",
    "serialization-structured-output",
    "unexpected-tool-result",
}
_MODES = {
    "application-replay",
    "offline-predicate-reproduction",
}
_CORE_ROLES = {
    "dependency-inventory",
    "export",
    "minimality-report",
    "original-capsule",
    "permission-record",
    "predicate",
    "reduced-capsule",
    "reduction-report",
}
_APPLICATION_ROLES = {
    "application-entrypoint",
    "application-replay-report",
}
_ALLOWED_ROLES = _CORE_ROLES | _APPLICATION_ROLES


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _text(value: Any, *, label: str, maximum: int = 4096) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or "\x00" in value
    ):
        raise ValueError(f"case-study {label} is invalid")
    return value


def _exact_object(
    value: Any,
    *,
    keys: set[str],
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"case-study {label} has an invalid shape")
    return value


def _validate_environment(value: Any) -> None:
    environment = _exact_object(
        value,
        keys={
            "architecture",
            "framework",
            "framework_version",
            "operating_system",
            "python",
        },
        label="environment",
    )
    for key, item in environment.items():
        _text(item, label=f"environment {key}", maximum=256)


def _validate_execution(value: Any) -> str:
    execution = _exact_object(
        value,
        keys={
            "command",
            "expected_exit_code",
            "mode",
            "what_materialized",
            "what_reexecuted",
        },
        label="execution",
    )
    mode = execution["mode"]
    if mode not in _MODES:
        raise ValueError("case-study execution mode is invalid")
    command = execution["command"]
    if not isinstance(command, list) or not 1 <= len(command) <= 32:
        raise ValueError("case-study execution command is invalid")
    for argument in command:
        _text(argument, label="execution command argument", maximum=512)
    exit_code = execution["expected_exit_code"]
    if (
        not isinstance(exit_code, int)
        or isinstance(exit_code, bool)
        or not -255 <= exit_code <= 255
    ):
        raise ValueError("case-study expected exit code is invalid")
    for field in ("what_materialized", "what_reexecuted"):
        items = execution[field]
        if not isinstance(items, list) or not 1 <= len(items) <= 32:
            raise ValueError(f"case-study {field} is invalid")
        for item in items:
            _text(item, label=field, maximum=512)
    return cast(str, mode)


def _validate_explanation(value: Any) -> None:
    explanation = _exact_object(
        value,
        keys={"failure", "limitations", "removed", "retained"},
        label="explanation",
    )
    for key, item in explanation.items():
        _text(item, label=f"explanation {key}")


def _validate_permission(value: Any) -> str:
    permission = _exact_object(
        value,
        keys={
            "data_owner_reference",
            "disclosure_review_date",
            "permission_record",
            "publication_scope",
            "reviewer_reference",
        },
        label="permission",
    )
    for key in (
        "data_owner_reference",
        "publication_scope",
        "reviewer_reference",
    ):
        _text(permission[key], label=f"permission {key}", maximum=512)
    date_value = _text(
        permission["disclosure_review_date"],
        label="disclosure review date",
        maximum=10,
    )
    try:
        if date.fromisoformat(date_value).isoformat() != date_value:
            raise ValueError
    except ValueError as exc:
        raise ValueError("case-study disclosure review date is invalid") from exc
    permission_record = _text(
        permission["permission_record"],
        label="permission record",
        maximum=512,
    )
    safe_relative_path(permission_record, label="case-study permission record")
    return permission_record


def _validate_artifacts(
    root: Path,
    value: Any,
    *,
    mode: str,
    permission_record: str,
) -> list[Path]:
    if not isinstance(value, list) or not 1 <= len(value) <= 32:
        raise ValueError("case-study artifacts are invalid")
    paths: list[Path] = []
    roles: set[str] = set()
    relative_paths: set[str] = set()
    total = 0
    permission_path: str | None = None
    for item in value:
        artifact = _exact_object(
            item,
            keys={"bytes", "path", "role", "sha256"},
            label="artifact",
        )
        role = artifact["role"]
        relative = artifact["path"]
        size = artifact["bytes"]
        digest = artifact["sha256"]
        if (
            role not in _ALLOWED_ROLES
            or role in roles
            or not isinstance(relative, str)
            or relative in relative_paths
            or not isinstance(size, int)
            or isinstance(size, bool)
            or not 0 <= size <= _MAX_ARTIFACT_BYTES
            or not isinstance(digest, str)
            or _DIGEST.fullmatch(digest) is None
        ):
            raise ValueError("case-study artifact identity is invalid")
        safe_relative_path(relative, label="case-study artifact")
        target = ensure_regular_file(root / relative, label="case-study artifact")
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError("case-study artifact escapes its directory") from exc
        if target.stat().st_size != size or _sha256(target) != digest:
            raise ValueError(f"case-study artifact hash/size mismatch: {relative}")
        roles.add(role)
        relative_paths.add(relative)
        paths.append(target)
        total += size
        if total > _MAX_TOTAL_BYTES:
            raise ValueError("case-study artifacts exceed the total byte limit")
        if role == "permission-record":
            permission_path = relative
    required = set(_CORE_ROLES)
    if mode == "application-replay":
        required.update(_APPLICATION_ROLES)
    if not required.issubset(roles):
        raise ValueError("case-study required artifact roles are missing")
    if permission_path != permission_record:
        raise ValueError("case-study permission record does not match its artifact")
    return paths


def verify_case_study_package(directory: Path) -> dict[str, Any]:
    root = ensure_real_directory(directory, label="case-study directory")
    manifest_path = ensure_regular_file(
        root / "case-study.json",
        label="case-study manifest",
    )
    if manifest_path.stat().st_size > _MAX_MANIFEST_BYTES:
        raise ValueError("case-study manifest is oversized")
    raw = manifest_path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("case-study manifest is invalid JSON") from exc
    manifest = _exact_object(
        value,
        keys={
            "artifacts",
            "case_id",
            "category",
            "environment",
            "execution",
            "explanation",
            "permission",
            "schema_version",
            "synthetic",
            "title",
        },
        label="manifest",
    )
    if canonical_json(manifest) != raw:
        raise ValueError("case-study manifest is not canonical JSON")
    if manifest["schema_version"] != 1:
        raise ValueError("unsupported case-study schema version")
    case_id = manifest["case_id"]
    if (
        not isinstance(case_id, str)
        or len(case_id) > 80
        or _CASE_ID.fullmatch(case_id) is None
    ):
        raise ValueError("case-study case ID is invalid")
    category = manifest["category"]
    if category not in _CATEGORIES:
        raise ValueError("case-study category is invalid")
    if manifest["synthetic"] is not False:
        raise ValueError("real case-study package must not be synthetic")
    _text(manifest["title"], label="title", maximum=256)
    _validate_environment(manifest["environment"])
    mode = _validate_execution(manifest["execution"])
    _validate_explanation(manifest["explanation"])
    permission_record = _validate_permission(manifest["permission"])
    artifacts = _validate_artifacts(
        root,
        manifest["artifacts"],
        mode=mode,
        permission_record=permission_record,
    )
    declared_paths = {
        manifest_path.relative_to(root).as_posix(),
        *(path.relative_to(root).as_posix() for path in artifacts),
    }
    actual_paths: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("case-study package contains a symbolic link")
        if path.is_file():
            actual_paths.add(path.relative_to(root).as_posix())
        elif path.is_dir():
            ensure_real_directory(path, label="case-study package directory")
        else:
            raise ValueError("case-study package contains an unsupported entry")
    if actual_paths != declared_paths:
        raise ValueError("case-study package file inventory is incomplete")
    return {
        "artifact_count": len(artifacts),
        "case_id": case_id,
        "category": category,
        "execution_mode": mode,
        "manifest_sha256": _sha256(manifest_path),
        "permission_measurement": (
            "declared-record-present; human authenticity review required"
        ),
        "schema_version": 1,
        "structurally_valid": True,
    }


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        print(
            "usage: python -m scripts.verify_case_study CASE_STUDY_DIRECTORY",
            file=sys.stderr,
        )
        return 2
    try:
        report = verify_case_study_package(Path(arguments[0]))
    except (OSError, TypeError, ValueError) as exc:
        print(f"case-study structural verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
