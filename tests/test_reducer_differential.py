from __future__ import annotations

import itertools
from dataclasses import replace

from hypothesis import given, settings
from hypothesis import strategies as st

from runsieve.capsule import capsule_bytes
from runsieve.ddmin import PredicateResult
from runsieve.hierarchy import minimize_capsule
from runsieve.schema import Capsule, Event, JsonValue, validate_capsule
from runsieve.verify import verify_one_minimal


def _contains_failure(value: JsonValue) -> bool:
    if isinstance(value, dict):
        return value.get("failure") is True or any(
            _contains_failure(child) for child in value.values()
        )
    if isinstance(value, list):
        return any(_contains_failure(child) for child in value)
    return False


def _predicate(capsule: Capsule) -> PredicateResult:
    try:
        validate_capsule(capsule)
    except ValueError:
        return PredicateResult.INVALID
    return (
        PredicateResult.REPRODUCES
        if any(_contains_failure(event.payload) for event in capsule.events)
        else PredicateResult.ABSENT
    )


@st.composite
def _valid_graphs(draw: st.DrawFn) -> tuple[Capsule, tuple[str, ...]]:
    count = draw(st.integers(min_value=1, max_value=5))
    kinds = draw(
        st.lists(
            st.sampled_from(("message", "span", "model_pair", "tool_pair")),
            min_size=count,
            max_size=count,
        )
    )
    target = draw(st.integers(min_value=0, max_value=count - 1))
    prefix = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Lu", "Nd"),
                min_codepoint=48,
                max_codepoint=122,
            ),
            min_size=1,
            max_size=8,
        )
    )
    events: list[Event] = [Event("run", "run", None, 0, {"suite": "differential"})]
    roots: list[str] = []
    sequence = 1
    for index, kind in enumerate(kinds):
        root = f"{prefix}-{index}-root"
        roots.append(root)
        failure = index == target
        if kind == "message":
            events.append(
                Event(
                    root,
                    "message",
                    "run",
                    sequence,
                    {"failure": failure, "noise": index},
                )
            )
            sequence += 1
        elif kind == "span":
            events.append(
                Event(
                    root,
                    "unknown",
                    "run",
                    sequence,
                    {"failure": failure, "noise": index, "unit": "span"},
                )
            )
            sequence += 1
        elif kind == "model_pair":
            response = f"{prefix}-{index}-response"
            events.extend(
                (
                    Event(
                        root,
                        "model_request",
                        "run",
                        sequence,
                        {"input": [{"content": str(index), "role": "user"}]},
                    ),
                    Event(
                        response,
                        "model_response",
                        "run",
                        sequence + 1,
                        {"output": {"failure": failure, "noise": index}},
                        (root,),
                    ),
                )
            )
            sequence += 2
        else:
            result = f"{prefix}-{index}-result"
            events.extend(
                (
                    Event(
                        root,
                        "tool_call",
                        "run",
                        sequence,
                        {"arguments": {"index": index}, "name": "probe"},
                    ),
                    Event(
                        result,
                        "tool_result",
                        "run",
                        sequence + 1,
                        {
                            "name": "probe",
                            "output": {"failure": failure, "noise": index},
                        },
                        (root,),
                    ),
                )
            )
            sequence += 2
    capsule = Capsule(
        schema_version="1",
        trace_id="trace_differential",
        events=tuple(events),
        metadata={"generated": True},
    )
    validate_capsule(capsule)
    return capsule, tuple(roots)


def _oracle_remove(capsule: Capsule, requested: set[str]) -> Capsule:
    removed = set(requested)
    while True:
        expanded = {
            event.id
            for event in capsule.events
            if event.id in removed
            or event.parent_id in removed
            or any(dependency in removed for dependency in event.dependencies)
        }
        if expanded == removed:
            break
        removed = expanded
    events = tuple(
        replace(event, sequence=sequence)
        for sequence, event in enumerate(
            event for event in capsule.events if event.id not in removed
        )
    )
    candidate = replace(capsule, events=events)
    validate_capsule(candidate)
    return candidate


def _exhaustive_event_oracle(capsule: Capsule, roots: tuple[str, ...]) -> Capsule:
    reproducing: list[Capsule] = []
    for count in range(len(roots) + 1):
        for removed in itertools.combinations(roots, count):
            candidate = _oracle_remove(capsule, set(removed))
            if _predicate(candidate) is PredicateResult.REPRODUCES:
                reproducing.append(candidate)
    return min(reproducing, key=lambda candidate: len(candidate.events))


def _rename_ids(capsule: Capsule) -> Capsule:
    renamed = {event.id: f"renamed-{index}" for index, event in enumerate(capsule.events)}
    return replace(
        capsule,
        events=tuple(
            replace(
                event,
                id=renamed[event.id],
                parent_id=renamed[event.parent_id] if event.parent_id is not None else None,
                dependencies=tuple(renamed[item] for item in event.dependencies),
            )
            for event in capsule.events
        ),
    )


@given(_valid_graphs())
@settings(max_examples=60, deadline=None)
def test_reducer_verifier_and_exhaustive_oracle_agree(
    generated: tuple[Capsule, tuple[str, ...]],
) -> None:
    source, roots = generated
    first = minimize_capsule(source, _predicate, predicate_identity="generated-v1")
    second = minimize_capsule(source, _predicate, predicate_identity="generated-v1")
    oracle = _exhaustive_event_oracle(source, roots)

    validate_capsule(first.capsule)
    assert _predicate(first.capsule) is PredicateResult.REPRODUCES
    assert capsule_bytes(first.capsule) == capsule_bytes(second.capsule)
    assert len(first.capsule.events) == len(oracle.events)
    assert verify_one_minimal(first.capsule, _predicate).is_one_minimal

    renamed = minimize_capsule(
        _rename_ids(source),
        _predicate,
        predicate_identity="generated-v1",
    )
    assert [event.kind for event in first.capsule.events] == [
        event.kind for event in renamed.capsule.events
    ]
    assert [event.payload for event in first.capsule.events] == [
        event.payload for event in renamed.capsule.events
    ]

    other_identity = minimize_capsule(
        source,
        _predicate,
        predicate_identity="generated-v2",
    )
    assert first.report.cache_key != other_identity.report.cache_key
    assert first.report.to_json().get("cache_key_complete") is True

    reordered_metadata = replace(
        source,
        metadata=dict(reversed(tuple(source.metadata.items()))),
    )
    assert capsule_bytes(source) == capsule_bytes(reordered_metadata)
