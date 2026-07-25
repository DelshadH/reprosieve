from __future__ import annotations

from runsieve.capsule import capsule_bytes
from runsieve.ddmin import PredicateResult
from runsieve.fixtures import killer_capsule, killer_predicate
from runsieve.hierarchy import minimize_capsule
from runsieve.schema import Capsule, Event, validate_capsule
from runsieve.verify import verify_one_minimal


def test_real_247_event_fixture_reduces_to_at_most_ten_and_is_one_minimal() -> None:
    source = killer_capsule()
    assert len(source.events) == 247
    validate_capsule(source)

    result = minimize_capsule(source, killer_predicate)
    assert len(source.events) == 247
    assert len(result.capsule.events) <= 10
    assert killer_predicate(result.capsule) is PredicateResult.REPRODUCES
    validate_capsule(result.capsule)

    proof = verify_one_minimal(result.capsule, killer_predicate)
    assert proof.is_one_minimal
    assert proof.reproducing_deletions == ()
    assert proof.attempts
    assert {attempt.result for attempt in proof.attempts} <= {
        PredicateResult.ABSENT,
        PredicateResult.INVALID,
    }
    assert all(attempt.reason for attempt in proof.attempts)


def test_minimality_proof_records_predicate_invalid_reasons() -> None:
    capsule = Capsule(
        schema_version="1",
        trace_id="trace_invalid_reason",
        events=(
            Event("run", "run", None, 0, {}),
            Event("failure", "error", "run", 1, {"needle": True}),
        ),
        metadata={},
    )

    def predicate(candidate: Capsule) -> PredicateResult:
        if len(candidate.events) != 2:
            return PredicateResult.INVALID
        failure = candidate.events[1]
        return (
            PredicateResult.REPRODUCES
            if failure.payload == {"needle": True}
            else PredicateResult.ABSENT
        )

    proof = verify_one_minimal(capsule, predicate)

    assert proof.is_one_minimal
    assert proof.attempts[0].result is PredicateResult.INVALID
    assert proof.attempts[0].reason == "predicate_invalid"
    assert proof.attempts[0].to_json()["reason"] == "predicate_invalid"


def _hierarchy_fixture() -> Capsule:
    return Capsule(
        schema_version="1",
        trace_id="trace_hierarchy",
        events=(
            Event("run", "run", None, 0, {}),
            Event("noise-branch", "unknown", "run", 1, {"unit": "span"}),
            Event("noise-child", "message", "noise-branch", 2, {"text": "noise"}),
            Event("noise-message", "message", "run", 3, {"text": "noise"}),
            Event("noise-call", "tool_call", "run", 4, {"name": "unused"}),
            Event(
                "noise-result",
                "tool_result",
                "run",
                5,
                {"name": "unused", "output": "noise"},
                ("noise-call",),
            ),
            Event("target-call", "tool_call", "run", 6, {"name": "probe", "extra": "drop"}),
            Event(
                "target-result",
                "tool_result",
                "run",
                7,
                {
                    "name": "probe",
                    "output": {"failure": "needle", "extra": "drop"},
                    "items": ["drop", "needle"],
                    "note": ("prefix-" * 12) + "needle" + ("-suffix" * 12),
                },
                ("target-call",),
            ),
        ),
        metadata={"fixture": "hierarchy"},
        workspace={
            "unused.txt": "drop",
            "needed.txt": ("A" * 96) + "needle" + ("B" * 96),
        },
        environment={"KEEP": "yes", "DROP": "no"},
    )


def _hierarchy_predicate(capsule: Capsule) -> PredicateResult:
    try:
        validate_capsule(capsule)
    except ValueError:
        return PredicateResult.INVALID
    result = next((event for event in capsule.events if event.id == "target-result"), None)
    if result is None or not isinstance(result.payload, dict):
        return PredicateResult.ABSENT
    output = result.payload.get("output")
    items = result.payload.get("items")
    note = result.payload.get("note")
    conditions = (
        isinstance(output, dict)
        and output.get("failure") == "needle"
        and isinstance(items, list)
        and "needle" in items
        and isinstance(note, str)
        and "needle" in note
        and "needle" in capsule.workspace.get("needed.txt", "")
        and capsule.environment.get("KEEP") == "yes"
    )
    return PredicateResult.REPRODUCES if conditions else PredicateResult.ABSENT


def test_each_hierarchy_level_accepts_a_real_reduction() -> None:
    result = minimize_capsule(_hierarchy_fixture(), _hierarchy_predicate)
    levels = {level.name: level for level in result.report.levels}
    for name in (
        "spans",
        "messages",
        "tool_pairs",
        "json_fields",
        "json_items",
        "text_chunks",
        "files",
        "file_chunks",
        "environment",
    ):
        assert levels[name].accepted > 0, name
    assert _hierarchy_predicate(result.capsule) is PredicateResult.REPRODUCES
    assert "noise-branch" not in {event.id for event in result.capsule.events}
    assert "noise-call" not in {event.id for event in result.capsule.events}
    assert set(result.capsule.workspace) == {"needed.txt"}
    assert result.capsule.environment == {"KEEP": "yes"}


def test_reduction_and_minimality_reports_define_their_measured_scope() -> None:
    source = _hierarchy_fixture()
    result = minimize_capsule(source, _hierarchy_predicate)
    report = result.report.to_json()

    assert report.get("source_bytes") == len(capsule_bytes(source))
    assert report.get("result_bytes") == len(capsule_bytes(result.capsule))
    assert isinstance(report.get("cache_key"), str)
    assert len(str(report["cache_key"])) == 64
    assert report.get("cache_key_complete") is False
    assert report.get("not_minimized") == [
        "archive_container",
        "capsule_metadata",
        "predicate_definition",
        "redaction_report",
    ]
    for level in report["levels"]:
        assert level["attempted"] >= level["accepted"]
        assert level["attempted"] == (
            level["accepted_candidates"]
            + level["rejected_candidates"]
            + level["invalid_candidates"]
            + level["cache_hits"]
        )

    proof = verify_one_minimal(result.capsule, _hierarchy_predicate).to_json()
    assert proof.get("definition") == (
        "Deleting any one remaining declared final-granularity unit makes the "
        "failure absent or the candidate invalid."
    )
    assert proof.get("not_minimized") == report["not_minimized"]


def test_invalid_candidates_are_never_accepted() -> None:
    capsule = Capsule(
        schema_version="1",
        trace_id="trace_invalid",
        events=(
            Event("run", "run", None, 0, {}),
            Event("required-parent", "unknown", "run", 1, {"unit": "span"}),
            Event("failure", "error", "required-parent", 2, {"needle": True}),
        ),
        metadata={},
    )

    def predicate(candidate: Capsule) -> PredicateResult:
        ids = {event.id for event in candidate.events}
        if "failure" in ids and "required-parent" not in ids:
            return PredicateResult.INVALID
        if not {"required-parent", "failure"} <= ids:
            return PredicateResult.ABSENT
        failure = next(event for event in candidate.events if event.id == "failure")
        if failure.payload != {"needle": True}:
            return PredicateResult.INVALID
        return PredicateResult.REPRODUCES

    result = minimize_capsule(capsule, predicate)
    assert {event.id for event in result.capsule.events} == {
        "run",
        "required-parent",
        "failure",
    }
    invalids = sum(
        int(level.to_json().get("invalid_candidates", 0))
        for level in result.report.levels
    )
    assert invalids > 0
