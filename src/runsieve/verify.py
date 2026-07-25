from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from .ddmin import PredicateResult
from .hierarchy import (
    delete_json_path,
    json_field_paths,
    json_item_paths,
    remove_events,
    replace_json_path,
    text_paths,
    value_at_json_path,
)
from .schema import Capsule, JsonValue, validate_capsule

Predicate = Callable[[Capsule], PredicateResult]
_CHUNK = 32


@dataclass(frozen=True, slots=True)
class VerificationAttempt:
    unit: str
    result: PredicateResult
    reason: str

    def to_json(self) -> dict[str, JsonValue]:
        return {"reason": self.reason, "result": self.result.value, "unit": self.unit}


@dataclass(frozen=True, slots=True)
class MinimalityProof:
    is_one_minimal: bool
    attempts: tuple[VerificationAttempt, ...]
    reproducing_deletions: tuple[str, ...]

    def to_json(self) -> dict[str, JsonValue]:
        return {
            "attempts": [attempt.to_json() for attempt in self.attempts],
            "is_one_minimal": self.is_one_minimal,
            "reproducing_deletions": list(self.reproducing_deletions),
        }


def _event_payload(capsule: Capsule, event_id: str, payload: JsonValue) -> Capsule:
    return replace(
        capsule,
        events=tuple(
            replace(event, payload=payload) if event.id == event_id else event
            for event in capsule.events
        ),
    )


def _attempt(
    candidate: Capsule,
    unit: str,
    predicate: Predicate,
) -> VerificationAttempt:
    try:
        validate_capsule(candidate)
    except ValueError:
        return VerificationAttempt(unit, PredicateResult.INVALID, "structural_invalid")
    result = predicate(candidate)
    if not isinstance(result, PredicateResult):
        raise TypeError("predicate must return PredicateResult")
    reason = {
        PredicateResult.REPRODUCES: "deletion_reproduced",
        PredicateResult.ABSENT: "failure_absent",
        PredicateResult.INVALID: "predicate_invalid",
    }[result]
    return VerificationAttempt(unit, result, reason)


def _chunks(value: str) -> tuple[str, ...]:
    return tuple(value[index : index + _CHUNK] for index in range(0, len(value), _CHUNK))


def verify_one_minimal(capsule: Capsule, predicate: Predicate) -> MinimalityProof:
    """Independently try every declared final-granularity deletion once."""
    validate_capsule(capsule)
    if predicate(capsule) is not PredicateResult.REPRODUCES:
        raise ValueError("capsule does not reproduce before verification")
    attempts: list[VerificationAttempt] = []

    for event in capsule.events:
        if event.kind == "run":
            continue
        attempts.append(
            _attempt(
                remove_events(capsule, {event.id}),
                f"event:{event.id}",
                predicate,
            )
        )

    for event in capsule.events:
        for category, paths in (
            ("json_field", json_field_paths(event.payload)),
            ("json_item", json_item_paths(event.payload)),
        ):
            for path in paths:
                candidate = _event_payload(
                    capsule,
                    event.id,
                    delete_json_path(event.payload, path),
                )
                attempts.append(
                    _attempt(candidate, f"{category}:{event.id}:{path!r}", predicate)
                )
        for path in text_paths(event.payload):
            value = value_at_json_path(event.payload, path)
            if not isinstance(value, str):
                continue
            chunks = _chunks(value)
            for index in range(len(chunks)):
                replacement = "".join(chunks[:index] + chunks[index + 1 :])
                candidate = _event_payload(
                    capsule,
                    event.id,
                    replace_json_path(event.payload, path, replacement),
                )
                attempts.append(
                    _attempt(candidate, f"text_chunk:{event.id}:{path!r}:{index}", predicate)
                )

    for name, content in capsule.workspace.items():
        workspace = dict(capsule.workspace)
        del workspace[name]
        attempts.append(_attempt(replace(capsule, workspace=workspace), f"file:{name}", predicate))
        chunks = _chunks(content)
        for index in range(len(chunks)):
            workspace = dict(capsule.workspace)
            workspace[name] = "".join(chunks[:index] + chunks[index + 1 :])
            attempts.append(
                _attempt(
                    replace(capsule, workspace=workspace),
                    f"file_chunk:{name}:{index}",
                    predicate,
                )
            )

    for name in capsule.environment:
        environment = dict(capsule.environment)
        del environment[name]
        attempts.append(
            _attempt(replace(capsule, environment=environment), f"environment:{name}", predicate)
        )

    reproducing = tuple(
        attempt.unit for attempt in attempts if attempt.result is PredicateResult.REPRODUCES
    )
    return MinimalityProof(
        is_one_minimal=not reproducing,
        attempts=tuple(attempts),
        reproducing_deletions=reproducing,
    )
