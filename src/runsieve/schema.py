from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

JsonPrimitive: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
EventKind: TypeAlias = Literal[
    "run",
    "model_request",
    "model_response",
    "tool_call",
    "tool_result",
    "handoff",
    "guardrail",
    "error",
    "unknown",
]


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


def validate_capsule(capsule: Capsule) -> None:
    ids = [event.id for event in capsule.events]
    if len(ids) != len(set(ids)):
        raise ValueError("event IDs must be unique")
    seen: set[str] = set()
    last_sequence = -1
    for event in capsule.events:
        if event.sequence <= last_sequence:
            raise ValueError("event sequence must be strictly increasing")
        last_sequence = event.sequence
        if event.parent_id is not None and event.parent_id not in seen:
            raise ValueError(f"event {event.id} references non-prior parent {event.parent_id}")
        missing = set(event.dependencies) - seen
        if missing:
            raise ValueError(f"event {event.id} has missing or future dependencies: {sorted(missing)}")
        seen.add(event.id)
