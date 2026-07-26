from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from typing import TypeVar

from .capsule import capsule_bytes
from .ddmin import PredicateResult, ddmin
from .schema import Capsule, Event, JsonValue, validate_capsule

Predicate = Callable[[Capsule], PredicateResult]
PathPart = str | int
JsonPath = tuple[PathPart, ...]
T = TypeVar("T")
_TEXT_CHUNK = 32
_FILE_CHUNK = 32
ONE_MINIMAL_DEFINITION = (
    "Deleting any one remaining declared final-granularity unit makes the "
    "failure absent or the candidate invalid."
)
NOT_MINIMIZED_SURFACES = (
    "archive_container",
    "capsule_metadata",
    "predicate_definition",
    "redaction_report",
)


@dataclass(frozen=True, slots=True)
class LevelReport:
    name: str
    before_units: int
    after_units: int
    accepted: int
    predicate_calls: int
    attempted: int
    accepted_candidates: int
    rejected_candidates: int
    invalid_candidates: int
    cache_hits: int
    invalid_reasons: dict[str, int]

    def to_json(self) -> dict[str, JsonValue]:
        invalid_reasons: dict[str, JsonValue] = dict(self.invalid_reasons)
        return {
            "accepted": self.accepted,
            "accepted_candidates": self.accepted_candidates,
            "after_units": self.after_units,
            "attempted": self.attempted,
            "before_units": self.before_units,
            "cache_hits": self.cache_hits,
            "invalid_candidates": self.invalid_candidates,
            "invalid_reasons": invalid_reasons,
            "name": self.name,
            "predicate_calls": self.predicate_calls,
            "rejected_candidates": self.rejected_candidates,
        }


@dataclass(frozen=True, slots=True)
class MinimizationReport:
    source_events: int
    result_events: int
    predicate_calls: int
    cache_hits: int
    wall_seconds: float
    levels: tuple[LevelReport, ...]
    source_bytes: int
    result_bytes: int
    cache_key: str
    cache_key_complete: bool

    def to_json(self) -> dict[str, JsonValue]:
        return {
            "cache_hits": self.cache_hits,
            "cache_key": self.cache_key,
            "cache_key_complete": self.cache_key_complete,
            "levels": [level.to_json() for level in self.levels],
            "not_minimized": list(NOT_MINIMIZED_SURFACES),
            "predicate_calls": self.predicate_calls,
            "result_bytes": self.result_bytes,
            "result_events": self.result_events,
            "source_bytes": self.source_bytes,
            "source_events": self.source_events,
            "wall_seconds": round(self.wall_seconds, 6),
        }


@dataclass(frozen=True, slots=True)
class MinimizationResult:
    capsule: Capsule
    report: MinimizationReport


class _MemoizedPredicate:
    def __init__(self, predicate: Predicate, *, cache_key: str) -> None:
        self.predicate = predicate
        self.cache_key = cache_key
        self.cache: dict[str, PredicateResult] = {}
        self.calls = 0
        self.cache_hits = 0
        self.requests = 0
        self.result_counts = {result: 0 for result in PredicateResult}
        self.invalid_reasons: dict[str, int] = {}

    def __call__(self, capsule: Capsule) -> PredicateResult:
        self.requests += 1
        try:
            validate_capsule(capsule)
            digest = hashlib.sha256(
                self.cache_key.encode("ascii") + capsule_bytes(capsule)
            ).hexdigest()
        except ValueError:
            self.result_counts[PredicateResult.INVALID] += 1
            self.invalid_reasons["structural_invalid"] = (
                self.invalid_reasons.get("structural_invalid", 0) + 1
            )
            return PredicateResult.INVALID
        cached = self.cache.get(digest)
        if cached is not None:
            self.cache_hits += 1
            return cached
        self.calls += 1
        result = self.predicate(capsule)
        if not isinstance(result, PredicateResult):
            raise TypeError("predicate must return PredicateResult")
        self.cache[digest] = result
        self.result_counts[result] += 1
        if result is PredicateResult.INVALID:
            self.invalid_reasons["predicate_invalid"] = (
                self.invalid_reasons.get("predicate_invalid", 0) + 1
            )
        return result


@dataclass(frozen=True, slots=True)
class _EvaluationSnapshot:
    requests: int
    calls: int
    cache_hits: int
    accepted: int
    rejected: int
    invalid: int
    invalid_reasons: dict[str, int]


def _snapshot(evaluate: _MemoizedPredicate) -> _EvaluationSnapshot:
    return _EvaluationSnapshot(
        requests=evaluate.requests,
        calls=evaluate.calls,
        cache_hits=evaluate.cache_hits,
        accepted=evaluate.result_counts[PredicateResult.REPRODUCES],
        rejected=evaluate.result_counts[PredicateResult.ABSENT],
        invalid=evaluate.result_counts[PredicateResult.INVALID],
        invalid_reasons=dict(evaluate.invalid_reasons),
    )


def _level_report(
    *,
    name: str,
    before_units: int,
    after_units: int,
    accepted: int,
    before: _EvaluationSnapshot,
    evaluate: _MemoizedPredicate,
) -> LevelReport:
    after = _snapshot(evaluate)
    reason_names = set(before.invalid_reasons) | set(after.invalid_reasons)
    invalid_reasons = {
        reason: after.invalid_reasons.get(reason, 0)
        - before.invalid_reasons.get(reason, 0)
        for reason in sorted(reason_names)
        if after.invalid_reasons.get(reason, 0)
        != before.invalid_reasons.get(reason, 0)
    }
    return LevelReport(
        name=name,
        before_units=before_units,
        after_units=after_units,
        accepted=accepted,
        predicate_calls=after.calls - before.calls,
        attempted=after.requests - before.requests,
        accepted_candidates=after.accepted - before.accepted,
        rejected_candidates=after.rejected - before.rejected,
        invalid_candidates=after.invalid - before.invalid,
        cache_hits=after.cache_hits - before.cache_hits,
        invalid_reasons=invalid_reasons,
    )


def _resequence(events: Iterable[Event]) -> tuple[Event, ...]:
    return tuple(replace(event, sequence=index) for index, event in enumerate(events))


def remove_events(capsule: Capsule, requested: set[str]) -> Capsule:
    """Remove events plus all parent/dependency consumers, preserving stable IDs."""
    protected = {event.id for event in capsule.events if event.kind == "run"}
    removed = set(requested) - protected
    changed = True
    while changed:
        changed = False
        for event in capsule.events:
            if event.id in removed or event.id in protected:
                continue
            if event.parent_id in removed or any(item in removed for item in event.dependencies):
                removed.add(event.id)
                changed = True
    events = _resequence(event for event in capsule.events if event.id not in removed)
    return replace(capsule, events=events)


def _reduce_units(
    current: Capsule,
    units: Sequence[T],
    build: Callable[[tuple[T, ...]], Capsule],
    evaluate: _MemoizedPredicate,
) -> tuple[Capsule, int]:
    if not units:
        return current, 0
    result = ddmin(tuple(units), lambda kept: evaluate(build(kept)))
    candidate = build(result.items)
    if candidate == current:
        return current, 0
    return candidate, len(units) - len(result.items)


def _event_level(
    current: Capsule,
    *,
    name: str,
    event_ids: Sequence[str],
    evaluate: _MemoizedPredicate,
) -> tuple[Capsule, LevelReport]:
    before = _snapshot(evaluate)
    all_units = tuple(event_ids)

    def build(kept: tuple[str, ...]) -> Capsule:
        return remove_events(current, set(all_units) - set(kept))

    result, accepted = _reduce_units(current, all_units, build, evaluate)
    remaining = len([event_id for event_id in all_units if event_id in {e.id for e in result.events}])
    return result, _level_report(
        name=name,
        before_units=len(all_units),
        after_units=remaining,
        accepted=accepted,
        before=before,
        evaluate=evaluate,
    )


def _json_paths(value: JsonValue, *, target: type[str | int]) -> list[JsonPath]:
    paths: list[JsonPath] = []

    def walk(current: JsonValue, path: JsonPath) -> None:
        if isinstance(current, dict):
            if current.get("$reprosieve_redacted") is True:
                return
            for key, child in current.items():
                if target is str:
                    paths.append((*path, key))
                walk(child, (*path, key))
        elif isinstance(current, list):
            for index, child in enumerate(current):
                if target is int:
                    paths.append((*path, index))
                walk(child, (*path, index))

    walk(value, ())
    return paths


def _text_paths(value: JsonValue) -> list[JsonPath]:
    paths: list[JsonPath] = []

    def walk(current: JsonValue, path: JsonPath) -> None:
        if isinstance(current, str):
            paths.append(path)
        elif isinstance(current, dict):
            if current.get("$reprosieve_redacted") is True:
                return
            for key, child in current.items():
                walk(child, (*path, key))
        elif isinstance(current, list):
            for index, child in enumerate(current):
                walk(child, (*path, index))

    walk(value, ())
    return paths


_DELETE = object()


def _replace_path(value: JsonValue, path: JsonPath, replacement: object) -> JsonValue:
    if not path:
        if replacement is _DELETE:
            raise ValueError("cannot delete a payload root")
        return replacement  # type: ignore[return-value]
    head, *tail = path
    if isinstance(head, str) and isinstance(value, dict) and head in value:
        output = dict(value)
        if not tail and replacement is _DELETE:
            del output[head]
        else:
            output[head] = _replace_path(output[head], tuple(tail), replacement)
        return output
    if isinstance(head, int) and isinstance(value, list) and 0 <= head < len(value):
        output_list = list(value)
        if not tail and replacement is _DELETE:
            del output_list[head]
        else:
            output_list[head] = _replace_path(output_list[head], tuple(tail), replacement)
        return output_list
    raise ValueError("JSON path no longer exists")


def _value_at(value: JsonValue, path: JsonPath) -> JsonValue:
    current = value
    for part in path:
        if isinstance(part, str):
            if not isinstance(current, dict):
                raise ValueError("JSON path no longer exists")
            current = current[part]
        elif not isinstance(current, list):
            raise ValueError("JSON path no longer exists")
        else:
            current = current[part]
    return current


def _replace_event_payload(capsule: Capsule, event_id: str, payload: JsonValue) -> Capsule:
    return replace(
        capsule,
        events=tuple(
            replace(event, payload=payload) if event.id == event_id else event
            for event in capsule.events
        ),
    )


def _greedy_json_level(
    current: Capsule,
    *,
    name: str,
    target: type[str | int],
    evaluate: _MemoizedPredicate,
) -> tuple[Capsule, LevelReport]:
    before = _snapshot(evaluate)
    initial_units = sum(len(_json_paths(event.payload, target=target)) for event in current.events)
    accepted = 0
    while True:
        changed = False
        for event in current.events:
            for path in _json_paths(event.payload, target=target):
                try:
                    payload = _replace_path(event.payload, path, _DELETE)
                except ValueError:
                    continue
                candidate = _replace_event_payload(current, event.id, payload)
                if evaluate(candidate) is PredicateResult.REPRODUCES:
                    current = candidate
                    accepted += 1
                    changed = True
                    break
            if changed:
                break
        if not changed:
            break
    remaining = sum(len(_json_paths(event.payload, target=target)) for event in current.events)
    return current, _level_report(
        name=name,
        before_units=initial_units,
        after_units=remaining,
        accepted=accepted,
        before=before,
        evaluate=evaluate,
    )


def _chunks(value: str, size: int) -> tuple[str, ...]:
    return tuple(value[index : index + size] for index in range(0, len(value), size))


def _text_level(
    current: Capsule,
    evaluate: _MemoizedPredicate,
) -> tuple[Capsule, LevelReport]:
    before = _snapshot(evaluate)
    before_units = sum(
        len(_chunks(value, _TEXT_CHUNK))
        for event in current.events
        for path in _text_paths(event.payload)
        if isinstance((value := _value_at(event.payload, path)), str)
    )
    accepted = 0
    for event_id in [event.id for event in current.events]:
        restart = True
        while restart:
            restart = False
            event = next(event for event in current.events if event.id == event_id)
            for path in _text_paths(event.payload):
                value = _value_at(event.payload, path)
                if not isinstance(value, str) or not value:
                    continue
                units = _chunks(value, _TEXT_CHUNK)
                base = current
                base_payload = event.payload
                selected_event_id = event_id
                selected_path = path

                def build(
                    kept: tuple[str, ...],
                    *,
                    fixed_base: Capsule = base,
                    fixed_payload: JsonValue = base_payload,
                    fixed_event_id: str = selected_event_id,
                    fixed_path: JsonPath = selected_path,
                ) -> Capsule:
                    payload = _replace_path(fixed_payload, fixed_path, "".join(kept))
                    return _replace_event_payload(fixed_base, fixed_event_id, payload)

                result = ddmin(units, lambda kept: evaluate(build(kept)))
                if result.items != units:
                    accepted += len(units) - len(result.items)
                    current = build(result.items)
                    restart = True
                    break
    after_units = sum(
        len(_chunks(value, _TEXT_CHUNK))
        for event in current.events
        for path in _text_paths(event.payload)
        if isinstance((value := _value_at(event.payload, path)), str)
    )
    return current, _level_report(
        name="text_chunks",
        before_units=before_units,
        after_units=after_units,
        accepted=accepted,
        before=before,
        evaluate=evaluate,
    )


def _file_level(
    current: Capsule,
    evaluate: _MemoizedPredicate,
) -> tuple[Capsule, LevelReport]:
    before = _snapshot(evaluate)
    units = tuple(sorted(current.workspace))

    def build(kept: tuple[str, ...]) -> Capsule:
        return replace(current, workspace={name: current.workspace[name] for name in kept})

    result, accepted = _reduce_units(current, units, build, evaluate)
    return result, _level_report(
        name="files",
        before_units=len(units),
        after_units=len(result.workspace),
        accepted=accepted,
        before=before,
        evaluate=evaluate,
    )


def _file_chunk_level(
    current: Capsule,
    evaluate: _MemoizedPredicate,
) -> tuple[Capsule, LevelReport]:
    before = _snapshot(evaluate)
    before_units = sum(len(_chunks(content, _FILE_CHUNK)) for content in current.workspace.values())
    accepted = 0
    for name in tuple(sorted(current.workspace)):
        content = current.workspace[name]
        units = _chunks(content, _FILE_CHUNK)
        if not units:
            continue
        base = current
        selected_name = name

        def build(
            kept: tuple[str, ...],
            *,
            fixed_base: Capsule = base,
            fixed_name: str = selected_name,
        ) -> Capsule:
            workspace = dict(fixed_base.workspace)
            workspace[fixed_name] = "".join(kept)
            return replace(fixed_base, workspace=workspace)

        result = ddmin(units, lambda kept: evaluate(build(kept)))
        if result.items != units:
            accepted += len(units) - len(result.items)
            current = build(result.items)
    after_units = sum(len(_chunks(content, _FILE_CHUNK)) for content in current.workspace.values())
    return current, _level_report(
        name="file_chunks",
        before_units=before_units,
        after_units=after_units,
        accepted=accepted,
        before=before,
        evaluate=evaluate,
    )


def _environment_level(
    current: Capsule,
    evaluate: _MemoizedPredicate,
) -> tuple[Capsule, LevelReport]:
    before = _snapshot(evaluate)
    units = tuple(sorted(current.environment))

    def build(kept: tuple[str, ...]) -> Capsule:
        return replace(current, environment={name: current.environment[name] for name in kept})

    result, accepted = _reduce_units(current, units, build, evaluate)
    return result, _level_report(
        name="environment",
        before_units=len(units),
        after_units=len(result.environment),
        accepted=accepted,
        before=before,
        evaluate=evaluate,
    )


def minimize_capsule(
    capsule: Capsule,
    predicate: Predicate,
    *,
    predicate_identity: str | None = None,
) -> MinimizationResult:
    validate_capsule(capsule)
    started = time.monotonic()
    source_data = capsule_bytes(capsule)
    identity = predicate_identity or (
        f"{getattr(predicate, '__module__', '<unknown>')}:"
        f"{getattr(predicate, '__qualname__', type(predicate).__qualname__)}"
    )
    cache_key = hashlib.sha256(
        b"reprosieve-reduction-cache-v1\0"
        + source_data
        + b"\0"
        + identity.encode("utf-8")
    ).hexdigest()
    evaluate = _MemoizedPredicate(predicate, cache_key=cache_key)
    if evaluate(capsule) is not PredicateResult.REPRODUCES:
        raise ValueError("initial capsule does not reproduce the target failure")
    current = capsule
    levels: list[LevelReport] = []

    child_counts: dict[str, int] = {}
    for event in current.events:
        if event.parent_id is not None:
            child_counts[event.parent_id] = child_counts.get(event.parent_id, 0) + 1
    span_ids = [
        event.id
        for event in current.events
        if event.kind in {"unknown", "handoff", "guardrail", "error"}
        and (
            child_counts.get(event.id, 0) > 0
            or (isinstance(event.payload, dict) and event.payload.get("unit") == "span")
        )
    ]
    current, report = _event_level(
        current,
        name="spans",
        event_ids=span_ids,
        evaluate=evaluate,
    )
    levels.append(report)

    current, report = _event_level(
        current,
        name="messages",
        event_ids=[event.id for event in current.events if event.kind == "message"],
        evaluate=evaluate,
    )
    levels.append(report)

    current, report = _event_level(
        current,
        name="tool_pairs",
        event_ids=[event.id for event in current.events if event.kind == "tool_call"],
        evaluate=evaluate,
    )
    levels.append(report)

    current, report = _event_level(
        current,
        name="model_pairs",
        event_ids=[event.id for event in current.events if event.kind == "model_request"],
        evaluate=evaluate,
    )
    levels.append(report)

    current, report = _greedy_json_level(
        current,
        name="json_fields",
        target=str,
        evaluate=evaluate,
    )
    levels.append(report)
    current, report = _greedy_json_level(
        current,
        name="json_items",
        target=int,
        evaluate=evaluate,
    )
    levels.append(report)
    current, report = _text_level(current, evaluate)
    levels.append(report)
    current, report = _file_level(current, evaluate)
    levels.append(report)
    current, report = _file_chunk_level(current, evaluate)
    levels.append(report)
    current, report = _environment_level(current, evaluate)
    levels.append(report)

    validate_capsule(current)
    if evaluate(current) is not PredicateResult.REPRODUCES:
        raise RuntimeError("minimization lost the target failure")
    return MinimizationResult(
        capsule=current,
        report=MinimizationReport(
            source_events=len(capsule.events),
            result_events=len(current.events),
            predicate_calls=evaluate.calls,
            cache_hits=evaluate.cache_hits,
            wall_seconds=time.monotonic() - started,
            levels=tuple(levels),
            source_bytes=len(source_data),
            result_bytes=len(capsule_bytes(current)),
            cache_key=cache_key,
            cache_key_complete=predicate_identity is not None,
        ),
    )


def json_field_paths(value: JsonValue) -> list[JsonPath]:
    return _json_paths(value, target=str)


def json_item_paths(value: JsonValue) -> list[JsonPath]:
    return _json_paths(value, target=int)


def text_paths(value: JsonValue) -> list[JsonPath]:
    return _text_paths(value)


def delete_json_path(value: JsonValue, path: JsonPath) -> JsonValue:
    return _replace_path(value, path, _DELETE)


def replace_json_path(value: JsonValue, path: JsonPath, replacement: JsonValue) -> JsonValue:
    return _replace_path(value, path, replacement)


def value_at_json_path(value: JsonValue, path: JsonPath) -> JsonValue:
    return _value_at(value, path)
