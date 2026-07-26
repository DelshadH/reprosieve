from __future__ import annotations

from reprosieve.schema import Capsule, Event


def sample_capsule(*, with_predicate: bool = False) -> Capsule:
    workspace: dict[str, str] = {}
    if with_predicate:
        workspace["verify_failure.py"] = (
            "import json, os, pathlib, sys\n"
            "replay = json.loads(pathlib.Path(os.environ['RUNSIEVE_REPLAY']).read_text())\n"
            "target = any(item.get('output', {}).get('failure') == 'needle' "
            "for item in replay['tool_outputs'])\n"
            "sys.exit(0 if target else 1)\n"
        )
    return Capsule(
        schema_version="1",
        trace_id="trace_demo",
        events=(
            Event("run", "run", None, 0, {"workflow_name": "demo"}),
            Event(
                "request",
                "model_request",
                "run",
                1,
                {"input": [{"role": "user", "content": "find failure"}]},
            ),
            Event(
                "response",
                "model_response",
                "run",
                2,
                {"output": [{"type": "function_call", "name": "probe"}]},
                ("request",),
            ),
            Event(
                "call",
                "tool_call",
                "run",
                3,
                {"name": "probe", "arguments": {"value": 7}},
                ("response",),
            ),
            Event(
                "result",
                "tool_result",
                "run",
                4,
                {"name": "probe", "output": {"failure": "needle"}},
                ("call",),
            ),
        ),
        metadata={"runtime": {"python": "3.11"}, "mode": "offline"},
        workspace=workspace,
        environment={"DEMO_FLAG": "1"},
    )
