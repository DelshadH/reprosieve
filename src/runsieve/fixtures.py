from __future__ import annotations

from .ddmin import PredicateResult
from .schema import Capsule, Event, validate_capsule


def killer_capsule() -> Capsule:
    """Return the public 247-event reduction fixture used by the release gate."""
    events: list[Event] = [
        Event("run", "run", None, 0, {"workflow_name": "killer-fixture"}),
        Event(
            "target-request",
            "model_request",
            "run",
            1,
            {"input": [{"role": "user", "content": "inspect the synthetic fixture"}]},
        ),
        Event(
            "target-response",
            "model_response",
            "run",
            2,
            {"output": [{"type": "function_call", "name": "probe"}]},
            ("target-request",),
        ),
        Event(
            "target-call",
            "tool_call",
            "run",
            3,
            {"name": "probe", "arguments": {"fixture": True, "noise": "discard"}},
            ("target-response",),
        ),
        Event(
            "target-result",
            "tool_result",
            "run",
            4,
            {
                "name": "probe",
                "output": {"failure": "needle", "diagnostic": "synthetic"},
            },
            ("target-call",),
        ),
    ]
    sequence = len(events)
    for branch_index in range(20):
        branch_id = f"noise-branch-{branch_index:02d}"
        events.append(
            Event(
                branch_id,
                "unknown",
                "run",
                sequence,
                {"unit": "span", "label": f"irrelevant branch {branch_index}"},
            )
        )
        sequence += 1
        for child_index in range(5):
            events.append(
                Event(
                    f"{branch_id}-message-{child_index}",
                    "message",
                    branch_id,
                    sequence,
                    {"text": f"irrelevant branch payload {branch_index}:{child_index}"},
                )
            )
            sequence += 1
    for message_index in range(122):
        events.append(
            Event(
                f"noise-message-{message_index:03d}",
                "message",
                "run",
                sequence,
                {
                    "role": "assistant" if message_index % 2 else "user",
                    "text": f"independent irrelevant message {message_index}",
                },
            )
        )
        sequence += 1
    capsule = Capsule(
        schema_version="1",
        trace_id="trace_killer_247",
        events=tuple(events),
        metadata={
            "fixture": "killer-247",
            "expected_max_events": 10,
            "application_replay": {
                "protocol": "runsieve-recorded-v1",
                "argv": ["python", "replay_application.py"],
            },
        },
        workspace={
            "replay_application.py": (
                "import json, os, pathlib\n"
                "from runsieve_replay_adapter import next_tool_output\n"
                "result={'failure':next_tool_output('probe').get('failure')}\n"
                "pathlib.Path(os.environ['RUNSIEVE_APPLICATION_RESULT']).write_text("
                "json.dumps(result),encoding='utf-8')\n"
            ),
            "verify_failure.py": (
                "import json, os, pathlib\n"
                "data=json.loads(pathlib.Path("
                "os.environ['RUNSIEVE_APPLICATION_RESULT']).read_text())\n"
                "ok=data.get('failure')=='needle'\n"
                "raise SystemExit(0 if ok else 1)\n"
            )
        },
    )
    if len(capsule.events) != 247:
        raise AssertionError("killer fixture must contain exactly 247 events")
    validate_capsule(capsule)
    return capsule


def killer_predicate(capsule: Capsule) -> PredicateResult:
    try:
        validate_capsule(capsule)
    except ValueError:
        return PredicateResult.INVALID
    for event in capsule.events:
        if event.id != "target-result" or not isinstance(event.payload, dict):
            continue
        output = event.payload.get("output")
        if isinstance(output, dict) and output.get("failure") == "needle":
            return PredicateResult.REPRODUCES
    return PredicateResult.ABSENT
