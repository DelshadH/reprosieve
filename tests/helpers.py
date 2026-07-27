from __future__ import annotations

import hashlib
import io
import json
import stat
import zipfile

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


def rewrite_capsule_members(data: bytes, updates: dict[str, bytes]) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = {
            info.filename: archive.read(info)
            for info in archive.infolist()
            if info.filename != "manifest.json"
        }
        manifest = json.loads(archive.read("manifest.json"))
    members.update(updates)
    entries: dict[str, dict[str, object]] = {}
    content = hashlib.sha256()
    for member_name, member_payload in sorted(members.items()):
        digest = hashlib.sha256(member_payload).hexdigest()
        entries[member_name] = {"sha256": digest, "size": len(member_payload)}
        content.update(member_name.encode("utf-8"))
        content.update(b"\0")
        content.update(bytes.fromhex(digest))
    manifest["entries"] = entries
    manifest["content_sha256"] = content.hexdigest()
    members["manifest.json"] = (
        json.dumps(manifest, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for member_name, member_payload in sorted(members.items()):
            info = zipfile.ZipInfo(member_name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            archive.writestr(info, member_payload)
    return output.getvalue()
