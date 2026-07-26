from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Literal, TypeAlias

JsonPrimitive: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
EventKind: TypeAlias = Literal[
    "run",
    "message",
    "model_request",
    "model_response",
    "tool_call",
    "tool_result",
    "handoff",
    "guardrail",
    "error",
    "unknown",
]

_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
_ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_WINDOWS_DEVICE_NAMES = {
    "aux",
    "con",
    "nul",
    "prn",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


@dataclass(frozen=True, slots=True)
class SchemaLimits:
    max_events: int = 10_000
    max_depth: int = 64
    max_nodes: int = 250_000
    max_string_bytes: int = 4 * 1024 * 1024
    max_workspace_files: int = 256
    max_workspace_bytes: int = 16 * 1024 * 1024
    max_environment_entries: int = 256
    max_json_bytes: int = 32 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class Event:
    id: str
    kind: EventKind
    parent_id: str | None
    sequence: int
    payload: JsonValue
    dependencies: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class Capsule:
    schema_version: Literal["1"]
    trace_id: str
    events: tuple[Event, ...]
    metadata: dict[str, JsonValue]
    workspace: dict[str, str] = field(default_factory=dict)
    environment: dict[str, str] = field(default_factory=dict)


def safe_relative_path(value: str, *, label: str = "path") -> str:
    """Return a normalized archive-style relative path or raise a generic error."""
    if not value or "\\" in value or "\x00" in value:
        raise ValueError(f"unsafe {label}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe {label}")
    if path.parts and path.parts[0].startswith("~"):
        raise ValueError(f"unsafe {label}")
    for part in path.parts:
        normalized_part = unicodedata.normalize("NFC", part)
        portable_part = normalized_part.rstrip(" .")
        if (
            normalized_part != part
            or portable_part != part
            or not portable_part
            or ":" in portable_part
            or portable_part.split(".", 1)[0].casefold() in _WINDOWS_DEVICE_NAMES
        ):
            raise ValueError(f"unsafe {label}")
    normalized = path.as_posix()
    if normalized != value:
        raise ValueError(f"unsafe {label}")
    return normalized


def _validate_json(value: JsonValue, *, limits: SchemaLimits, label: str) -> None:
    nodes = 0
    stack: list[tuple[object, int]] = [(value, 0)]
    active: set[int] = set()
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > limits.max_nodes:
            raise ValueError(f"{label} node limit exceeded")
        if depth > limits.max_depth:
            raise ValueError(f"{label} depth limit exceeded")
        if current is None or isinstance(current, (bool, int)):
            continue
        if isinstance(current, float):
            if not math.isfinite(current):
                raise ValueError(f"{label} contains a non-finite number")
            continue
        if isinstance(current, str):
            if len(current.encode("utf-8")) > limits.max_string_bytes:
                raise ValueError(f"{label} string limit exceeded")
            continue
        if isinstance(current, (list, dict)):
            identity = id(current)
            if identity in active:
                raise ValueError(f"{label} contains a cycle")
            active.add(identity)
            stack.append((_Leave(identity), depth))
            if isinstance(current, list):
                stack.extend((child, depth + 1) for child in reversed(current))
            else:
                for key, child in reversed(tuple(current.items())):
                    if not isinstance(key, str):
                        raise ValueError(f"{label} object keys must be strings")
                    if len(key.encode("utf-8")) > limits.max_string_bytes:
                        raise ValueError(f"{label} key limit exceeded")
                    stack.append((child, depth + 1))
            continue
        if isinstance(current, _Leave):
            active.discard(current.identity)
            continue
        raise ValueError(f"{label} contains a non-JSON value")

    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError(f"{label} is not valid bounded JSON") from error
    if len(encoded) > limits.max_json_bytes:
        raise ValueError(f"{label} JSON size limit exceeded")


@dataclass(frozen=True, slots=True)
class _Leave:
    identity: int


def validate_capsule(capsule: Capsule, *, limits: SchemaLimits | None = None) -> None:
    limits = limits or SchemaLimits()
    if capsule.schema_version != "1":
        raise ValueError("unsupported capsule schema version")
    if not _ID.fullmatch(capsule.trace_id):
        raise ValueError("invalid trace ID")
    if len(capsule.events) > limits.max_events:
        raise ValueError("capsule event limit exceeded")
    if not capsule.events:
        raise ValueError("capsule must contain at least one event")

    ids = [event.id for event in capsule.events]
    if len(ids) != len(set(ids)):
        raise ValueError("event IDs must be unique")
    event_kinds: dict[str, EventKind] = {}
    seen: set[str] = set()
    last_sequence = -1
    for event in capsule.events:
        if not _ID.fullmatch(event.id):
            raise ValueError("invalid event ID")
        if event.kind not in {
            "run",
            "message",
            "model_request",
            "model_response",
            "tool_call",
            "tool_result",
            "handoff",
            "guardrail",
            "error",
            "unknown",
        }:
            raise ValueError("unsupported event kind")
        if event.sequence <= last_sequence:
            raise ValueError("event sequence must be strictly increasing")
        last_sequence = event.sequence
        if event.parent_id is not None and event.parent_id not in seen:
            raise ValueError("event references a missing or future parent")
        if len(event.dependencies) != len(set(event.dependencies)):
            raise ValueError("event dependencies must be unique")
        missing = set(event.dependencies) - seen
        if missing:
            raise ValueError("event has missing or future dependencies")
        if event.id in event.dependencies:
            raise ValueError("event cannot depend on itself")
        if event.kind == "tool_result":
            producers = [item for item in event.dependencies if event_kinds[item] == "tool_call"]
            if len(producers) != 1:
                raise ValueError("tool result must reference exactly one tool call")
        if event.kind == "model_response":
            producers = [item for item in event.dependencies if event_kinds[item] == "model_request"]
            if len(producers) != 1:
                raise ValueError("model response must reference exactly one model request")
        _validate_json(event.payload, limits=limits, label="event payload")
        seen.add(event.id)
        event_kinds[event.id] = event.kind

    _validate_json(capsule.metadata, limits=limits, label="capsule metadata")
    if len(capsule.workspace) > limits.max_workspace_files:
        raise ValueError("workspace file limit exceeded")
    workspace_bytes = 0
    portable_workspace_paths: set[str] = set()
    for path, content in capsule.workspace.items():
        try:
            normalized_path = safe_relative_path(path, label="workspace path")
        except ValueError as error:
            raise ValueError("unsafe workspace path") from error
        portable_identity = "/".join(
            component.casefold()
            for component in PurePosixPath(normalized_path).parts
        )
        if portable_identity in portable_workspace_paths:
            raise ValueError("unsafe workspace path collision")
        portable_workspace_paths.add(portable_identity)
        if not isinstance(content, str):
            raise ValueError("workspace content must be UTF-8 text")
        workspace_bytes += len(content.encode("utf-8"))
        if workspace_bytes > limits.max_workspace_bytes:
            raise ValueError("workspace size limit exceeded")
    if len(capsule.environment) > limits.max_environment_entries:
        raise ValueError("environment entry limit exceeded")
    for name, value in capsule.environment.items():
        if not _ENVIRONMENT_NAME.fullmatch(name):
            raise ValueError("invalid environment entry name")
        if not isinstance(value, str):
            raise ValueError("environment values must be strings")
        if len(value.encode("utf-8")) > limits.max_string_bytes:
            raise ValueError("environment value limit exceeded")
