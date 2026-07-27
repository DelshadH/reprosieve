from __future__ import annotations

import hashlib
import io
import json
import stat
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Literal, cast

from .safeio import ensure_new_path, read_regular_file_bounded
from .schema import (
    Capsule,
    Event,
    EventKind,
    JsonValue,
    SchemaLimits,
    safe_relative_path,
    validate_capsule,
    validate_json_document,
)

_FORMAT = "reprosieve-capsule"
_FORMAT_VERSION = 1
_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_REQUIRED_MEMBERS = {
    "events/v1.json",
    "metadata.json",
    "environment.json",
    "workspace/index.json",
    "redaction.json",
    "predicate.json",
}


@dataclass(frozen=True, slots=True)
class CapsuleLimits:
    max_archive_bytes: int = 32 * 1024 * 1024
    max_member_bytes: int = 16 * 1024 * 1024
    max_total_bytes: int = 64 * 1024 * 1024
    max_members: int = 512
    max_ratio: float = 20.0
    schema: SchemaLimits = field(default_factory=SchemaLimits)


@dataclass(frozen=True, slots=True)
class CapsuleInfo:
    path: Path | None
    sha256: str
    size: int
    content_sha256: str


@dataclass(frozen=True, slots=True)
class CapsuleSnapshot:
    data: bytes
    capsule: Capsule
    _members: Mapping[str, bytes] = field(repr=False)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    def document(self, name: str) -> dict[str, Any]:
        if name not in {"redaction.json", "predicate.json"}:
            raise ValueError("unsupported capsule document")
        if name not in self._members:
            raise ValueError("capsule document is missing")
        return _require_dict(_load_json(self._members[name], label=name), label=name)


def canonical_json(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError("value is not canonical JSON") from error


def _event_json(event: Event) -> dict[str, object]:
    return {
        "dependencies": list(event.dependencies),
        "id": event.id,
        "kind": event.kind,
        "parent_id": event.parent_id,
        "payload": event.payload,
        "sequence": event.sequence,
    }


def _payload_members(
    capsule: Capsule,
    *,
    redaction_report: dict[str, JsonValue] | None,
    predicate: dict[str, JsonValue] | None,
) -> dict[str, bytes]:
    members = {
        "events/v1.json": canonical_json([_event_json(event) for event in capsule.events]),
        "metadata.json": canonical_json(capsule.metadata),
        "environment.json": canonical_json(capsule.environment),
        "workspace/index.json": canonical_json(sorted(capsule.workspace)),
        "redaction.json": canonical_json(redaction_report or {}),
        "predicate.json": canonical_json(predicate or {}),
    }
    for path, content in sorted(capsule.workspace.items()):
        safe_relative_path(path, label="workspace path")
        members[f"workspace/files/{path}"] = content.encode("utf-8")
    return members


def capsule_bytes(
    capsule: Capsule,
    *,
    redaction_report: dict[str, JsonValue] | None = None,
    predicate: dict[str, JsonValue] | None = None,
) -> bytes:
    validate_capsule(capsule)
    members = _payload_members(
        capsule,
        redaction_report=redaction_report,
        predicate=predicate,
    )
    content_digest = hashlib.sha256()
    manifest_entries: dict[str, dict[str, JsonValue]] = {}
    for name, payload in sorted(members.items()):
        digest = hashlib.sha256(payload).hexdigest()
        manifest_entries[name] = {"sha256": digest, "size": len(payload)}
        content_digest.update(name.encode("utf-8"))
        content_digest.update(b"\0")
        content_digest.update(bytes.fromhex(digest))
    manifest = {
        "content_sha256": content_digest.hexdigest(),
        "entries": manifest_entries,
        "format": _FORMAT,
        "format_version": _FORMAT_VERSION,
        "schema_version": capsule.schema_version,
        "trace_id": capsule.trace_id,
    }
    all_members = {"manifest.json": canonical_json(manifest), **members}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED, strict_timestamps=True) as archive:
        for name, payload in sorted(all_members.items()):
            info = zipfile.ZipInfo(name, date_time=_TIMESTAMP)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            archive.writestr(info, payload)
    return output.getvalue()


def write_capsule(
    capsule: Capsule,
    path: str | Path,
    *,
    redaction_report: dict[str, JsonValue] | None = None,
    predicate: dict[str, JsonValue] | None = None,
) -> CapsuleInfo:
    target = ensure_new_path(path, label="capsule output")
    data = capsule_bytes(capsule, redaction_report=redaction_report, predicate=predicate)
    with target.open("xb") as stream:
        stream.write(data)
    manifest = _read_manifest_from_bytes(data)
    return CapsuleInfo(
        path=target,
        sha256=hashlib.sha256(data).hexdigest(),
        size=len(data),
        content_sha256=str(manifest["content_sha256"]),
    )


def _safe_member(name: str) -> str:
    try:
        return safe_relative_path(name, label="archive member")
    except ValueError as error:
        raise ValueError("unsafe archive member") from error


def _load_json(payload: bytes, *, label: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in items:
            if key in output:
                raise ValueError(f"{label} contains duplicate object keys")
            output[key] = value
        return output

    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ValueError(f"{label} contains a non-finite number")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError(f"{label} is invalid JSON") from error


def _read_manifest_from_bytes(data: bytes) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            result = _load_json(archive.read("manifest.json"), label="manifest")
    except (KeyError, zipfile.BadZipFile, RuntimeError, OSError) as error:
        raise ValueError("capsule archive is corrupt") from error
    if not isinstance(result, dict):
        raise ValueError("capsule manifest must be an object")
    return result


def _validated_members(data: bytes, limits: CapsuleLimits) -> tuple[dict[str, bytes], dict[str, Any]]:
    if len(data) > limits.max_archive_bytes:
        raise ValueError("capsule archive size limit exceeded")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError) as error:
        raise ValueError("capsule archive is corrupt") from error
    with archive:
        infos = archive.infolist()
        if len(infos) > limits.max_members:
            raise ValueError("capsule archive member limit exceeded")
        names: set[str] = set()
        total = 0
        for info in infos:
            name = _safe_member(info.filename)
            if name in names:
                raise ValueError("capsule archive contains duplicate members")
            names.add(name)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError("capsule archive contains a symlink")
            if info.flag_bits & 0x1:
                raise ValueError("encrypted capsule members are unsupported")
            if info.file_size > limits.max_member_bytes:
                raise ValueError("capsule member size limit exceeded")
            total += info.file_size
            if total > limits.max_total_bytes:
                raise ValueError("capsule total size limit exceeded")
            ratio = info.file_size / max(1, info.compress_size)
            if ratio > limits.max_ratio:
                raise ValueError("capsule expansion ratio limit exceeded")
        if "manifest.json" not in names:
            raise ValueError("capsule manifest is missing")
        try:
            members = {info.filename: archive.read(info) for info in infos}
        except (zipfile.BadZipFile, RuntimeError, OSError, EOFError) as error:
            raise ValueError("capsule archive is corrupt") from error

    manifest = _load_json(members["manifest.json"], label="manifest")
    if not isinstance(manifest, dict):
        raise ValueError("capsule manifest must be an object")
    if manifest.get("format") != _FORMAT or manifest.get("format_version") != _FORMAT_VERSION:
        raise ValueError("unsupported capsule format")
    entries = manifest.get("entries")
    if not isinstance(entries, dict):
        raise ValueError("capsule manifest entries are invalid")
    expected_names = set(members) - {"manifest.json"}
    if set(entries) != expected_names:
        raise ValueError("capsule manifest does not cover every member")
    content_digest = hashlib.sha256()
    for name in sorted(expected_names):
        descriptor = entries.get(name)
        if not isinstance(descriptor, dict):
            raise ValueError("capsule manifest entry is invalid")
        payload = members[name]
        digest = hashlib.sha256(payload).hexdigest()
        if descriptor.get("sha256") != digest or descriptor.get("size") != len(payload):
            raise ValueError("capsule member hash mismatch")
        content_digest.update(name.encode("utf-8"))
        content_digest.update(b"\0")
        content_digest.update(bytes.fromhex(digest))
    if manifest.get("content_sha256") != content_digest.hexdigest():
        raise ValueError("capsule content hash mismatch")
    return members, manifest


def _require_dict(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _capsule_from_members(
    members: Mapping[str, bytes],
    manifest: Mapping[str, Any],
    *,
    limits: CapsuleLimits,
) -> Capsule:
    if not _REQUIRED_MEMBERS.issubset(members):
        raise ValueError("capsule is missing required members")
    unsupported_members = {
        name
        for name in members
        if name not in _REQUIRED_MEMBERS
        and name != "manifest.json"
        and not name.startswith("workspace/files/")
    }
    if unsupported_members:
        raise ValueError("capsule contains an unsupported capsule member")
    events_raw = _load_json(members["events/v1.json"], label="events")
    metadata = _require_dict(_load_json(members["metadata.json"], label="metadata"), label="metadata")
    environment = _require_dict(
        _load_json(members["environment.json"], label="environment"),
        label="environment",
    )
    redaction = _require_dict(
        _load_json(members["redaction.json"], label="redaction report"),
        label="redaction report",
    )
    predicate = _require_dict(
        _load_json(members["predicate.json"], label="predicate"),
        label="predicate",
    )
    validate_json_document(
        redaction,
        limits=limits.schema,
        label="redaction report",
    )
    validate_json_document(
        predicate,
        limits=limits.schema,
        label="predicate",
    )
    workspace_index = _load_json(members["workspace/index.json"], label="workspace index")
    if not isinstance(events_raw, list) or not isinstance(workspace_index, list):
        raise ValueError("capsule event or workspace index is invalid")
    workspace: dict[str, str] = {}
    workspace_identities: set[str] = set()
    for path_value in workspace_index:
        if not isinstance(path_value, str):
            raise ValueError("workspace index paths must be strings")
        path_name = safe_relative_path(path_value, label="workspace path")
        portable_identity = "/".join(
            component.casefold()
            for component in PurePosixPath(path_name).parts
        )
        if portable_identity in workspace_identities:
            raise ValueError("workspace path collision")
        workspace_identities.add(portable_identity)
        member_name = f"workspace/files/{path_name}"
        if member_name not in members:
            raise ValueError("workspace file is missing")
        try:
            workspace[path_name] = members[member_name].decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("workspace file is not UTF-8 text") from error
    expected_workspace = {f"workspace/files/{path}" for path in workspace}
    actual_workspace = {name for name in members if name.startswith("workspace/files/")}
    if actual_workspace != expected_workspace:
        raise ValueError("capsule contains undeclared workspace files")

    events: list[Event] = []
    for item in events_raw:
        raw = _require_dict(item, label="event")
        required = {"id", "kind", "parent_id", "sequence", "payload", "dependencies"}
        if set(raw) != required:
            raise ValueError("event fields are invalid")
        dependencies = raw["dependencies"]
        if not isinstance(dependencies, list) or not all(
            isinstance(dependency, str) for dependency in dependencies
        ):
            raise ValueError("event dependencies are invalid")
        if not isinstance(raw["id"], str) or not isinstance(raw["kind"], str):
            raise ValueError("event identity is invalid")
        if raw["parent_id"] is not None and not isinstance(raw["parent_id"], str):
            raise ValueError("event parent is invalid")
        if isinstance(raw["sequence"], bool) or not isinstance(raw["sequence"], int):
            raise ValueError("event sequence is invalid")
        events.append(
            Event(
                id=raw["id"],
                kind=cast(EventKind, raw["kind"]),
                parent_id=raw["parent_id"],
                sequence=raw["sequence"],
                payload=raw["payload"],
                dependencies=tuple(dependencies),
            )
        )
    schema_version = manifest.get("schema_version")
    trace_id = manifest.get("trace_id")
    if not isinstance(schema_version, str) or not isinstance(trace_id, str):
        raise ValueError("manifest capsule identity is invalid")
    capsule = Capsule(
        schema_version=cast(Literal["1"], schema_version),
        trace_id=trace_id,
        events=tuple(events),
        metadata=metadata,
        workspace={key: workspace[key] for key in sorted(workspace)},
        environment={str(key): value for key, value in environment.items()},
    )
    validate_capsule(capsule, limits=limits.schema)
    return capsule


def load_capsule_snapshot(
    path: str | Path,
    *,
    limits: CapsuleLimits | None = None,
) -> CapsuleSnapshot:
    selected_limits = limits or CapsuleLimits()
    data = read_regular_file_bounded(
        path,
        max_bytes=selected_limits.max_archive_bytes,
        label="capsule archive",
    )
    members, manifest = _validated_members(data, selected_limits)
    capsule = _capsule_from_members(members, manifest, limits=selected_limits)
    return CapsuleSnapshot(
        data=data,
        capsule=capsule,
        _members=MappingProxyType(members),
    )


def load_capsule(path: str | Path, *, limits: CapsuleLimits | None = None) -> Capsule:
    return load_capsule_snapshot(path, limits=limits).capsule


def capsule_file_sha256(path: str | Path) -> str:
    data = read_regular_file_bounded(
        path,
        max_bytes=CapsuleLimits().max_archive_bytes,
        label="capsule archive",
    )
    return hashlib.sha256(data).hexdigest()


def read_capsule_document(
    path: str | Path,
    name: str,
    *,
    limits: CapsuleLimits | None = None,
) -> dict[str, Any]:
    return load_capsule_snapshot(path, limits=limits).document(name)
