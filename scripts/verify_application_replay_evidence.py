from __future__ import annotations

import asyncio
import hashlib
import json
import re
import socket
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from agents import Agent, FunctionTool

from runsieve.adapters.openai_agents_replay import (
    ApplicationReplayDivergence,
    ApplicationReplayUnsupported,
    OpenAIAgentsReplaySession,
)
from runsieve.capsule import canonical_json, load_capsule
from runsieve.ddmin import PredicateResult
from runsieve.safeio import ensure_real_directory, ensure_regular_file
from runsieve.schema import Capsule, safe_relative_path
from runsieve.verify import verify_one_minimal

ROOT = Path(__file__).resolve().parents[1]
_SHA = re.compile(r"^[0-9a-f]{40}$")
_MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
_ASSERTIONS = (
    "application-executed",
    "all-interactions-consumed",
    "provider-canary-zero",
    "original-tool-canary-zero",
    "instruction-divergence",
    "input-divergence",
    "tool-schema-divergence",
    "argument-divergence",
    "ordering-divergence",
    "early-exit-divergence",
    "unsupported-surface-rejected",
    "caught-original-tool-attempt-rejected",
    "real-unit-reduced",
    "independent-one-minimal",
)


def _run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_document(path: Path, *, label: str) -> dict[str, Any]:
    if path.stat().st_size > _MAX_ARTIFACT_BYTES:
        raise ValueError(f"{label} is oversized")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is invalid JSON") from exc
    if not isinstance(value, dict) or canonical_json(value) != raw:
        raise ValueError(f"{label} is not canonical JSON")
    return value


def _artifact_paths(
    root: Path,
    manifest: dict[str, Any],
) -> dict[str, Path]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 3:
        raise ValueError("application replay evidence must contain exactly three artifacts")
    result: dict[str, Path] = {}
    seen_paths: set[str] = set()
    total = 0
    for item in artifacts:
        if not isinstance(item, dict) or set(item) != {"bytes", "path", "role", "sha256"}:
            raise ValueError("application replay evidence artifact has an invalid shape")
        role = item["role"]
        path_value = item["path"]
        size = item["bytes"]
        digest = item["sha256"]
        if (
            role not in {"source-capsule", "reduced-capsule", "producer-report"}
            or role in result
            or not isinstance(path_value, str)
            or path_value in seen_paths
            or not isinstance(size, int)
            or isinstance(size, bool)
            or not 0 <= size <= _MAX_ARTIFACT_BYTES
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise ValueError("application replay evidence artifact identity is invalid")
        safe_relative_path(path_value, label="application replay evidence artifact")
        target = ensure_regular_file(
            root / path_value,
            label="application replay evidence artifact",
        )
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError("application replay evidence artifact escapes its directory") from exc
        if target.stat().st_size != size or _sha256(target) != digest:
            raise ValueError(f"{role} hash/size mismatch")
        total += size
        if total > _MAX_ARTIFACT_BYTES:
            raise ValueError("application replay evidence artifacts are oversized")
        result[role] = target
        seen_paths.add(path_value)
    return result


def _tool(counter: dict[str, int]) -> FunctionTool:
    async def forbidden(_context: Any, _arguments: str) -> Any:
        counter["calls"] += 1
        raise AssertionError("independent verifier original tool executed")

    return FunctionTool(
        name="probe",
        description="Return a synthetic failure marker.",
        params_json_schema={
            "additionalProperties": False,
            "properties": {"value": {"type": "integer"}},
            "required": ["value"],
            "type": "object",
        },
        on_invoke_tool=forbidden,
    )


async def _application(session: Any, executions: dict[str, int]) -> Any:
    executions["calls"] += 1
    agent = Agent(
        name="RunSieve evidence application",
        instructions="Call probe once, then report the marker.",
        model=session.model,
        tools=list(session.tools),
    )
    return await session.run(agent, "find failure")


def _event_mutation(
    capsule: Capsule,
    *,
    kind: str,
    field: str,
    value: Any,
) -> Capsule:
    events = list(capsule.events)
    index = next(index for index, event in enumerate(events) if event.kind == kind)
    event = events[index]
    if not isinstance(event.payload, dict):
        raise ValueError("application replay mutation target is malformed")
    mutated = {**event.payload, field: value}
    if canonical_json(mutated) == canonical_json(event.payload):
        raise ValueError("application replay verifier mutation was a no-op")
    events[index] = replace(event, payload=mutated)
    return replace(capsule, events=tuple(events))


def _expect_divergence(
    capsule: Capsule,
    *,
    tool: FunctionTool,
    pattern: str,
) -> None:
    executions = {"calls": 0}
    try:
        _run(
            OpenAIAgentsReplaySession(
                capsule,
                original_tools=(tool,),
            ).execute(lambda session: _application(session, executions))
        )
    except ApplicationReplayDivergence as exc:
        if pattern not in str(exc):
            raise ValueError(f"unexpected application replay divergence: {exc}") from exc
    else:
        raise ValueError("application replay mutation did not diverge")
    if executions["calls"] != 1:
        raise ValueError("application replay divergence did not execute the application")


def _verify_replay(reduced: Capsule) -> dict[str, int]:
    original = {"calls": 0}
    network = {"calls": 0}
    executions = {"calls": 0}
    tool = _tool(original)
    original_create_connection = socket.create_connection
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def is_loopback(address: Any) -> bool:
        return (
            isinstance(address, tuple)
            and bool(address)
            and address[0] in {"127.0.0.1", "::1", "localhost"}
        )

    def guarded_create_connection(address: Any, *args: Any, **kwargs: Any) -> Any:
        if is_loopback(address):
            return original_create_connection(address, *args, **kwargs)
        network["calls"] += 1
        raise AssertionError("network canary touched during application replay")

    def guarded_connect(instance: socket.socket, address: Any) -> Any:
        if is_loopback(address):
            return original_connect(instance, address)
        network["calls"] += 1
        raise AssertionError("network canary touched during application replay")

    def guarded_connect_ex(instance: socket.socket, address: Any) -> Any:
        if is_loopback(address):
            return original_connect_ex(instance, address)
        network["calls"] += 1
        raise AssertionError("network canary touched during application replay")

    with (
        patch("socket.create_connection", guarded_create_connection),
        patch.object(socket.socket, "connect", guarded_connect),
        patch.object(socket.socket, "connect_ex", guarded_connect_ex),
    ):
        report = _run(
            OpenAIAgentsReplaySession(
                reduced,
                original_tools=(tool,),
            ).execute(lambda session: _application(session, executions))
        )
    if (
        executions["calls"] != 1
        or report.application_executions != 1
        or report.model_calls_consumed != 2
        or report.tool_calls_consumed != 1
        or report.provider_resolution_attempts != 0
        or report.original_tool_calls != 0
        or not report.all_interactions_consumed
        or report.final_output != "needle confirmed"
        or original["calls"] != 0
        or network["calls"] != 0
    ):
        raise ValueError("independent application replay measurement failed")
    return {
        "application_executions": executions["calls"],
        "network_calls": network["calls"],
        "original_tool_calls": original["calls"],
        "provider_resolution_attempts": report.provider_resolution_attempts,
    }


def _verify_caught_original_attempt(reduced: Capsule) -> None:
    original = {"calls": 0}
    tool = _tool(original)
    session = OpenAIAgentsReplaySession(reduced, original_tools=(tool,))

    async def unsafe_application(replay: Any) -> Any:
        try:
            await tool.on_invoke_tool(cast(Any, None), '{"value":7}')
        except ApplicationReplayDivergence:
            pass
        return await _application(replay, {"calls": 0})

    try:
        _run(session.execute(unsafe_application))
    except ApplicationReplayDivergence as exc:
        if "original tool execution" not in str(exc):
            raise ValueError(f"unexpected original-tool canary result: {exc}") from exc
    else:
        raise ValueError("caught original-tool attempt was not rejected")
    if session.original_tool_calls != 1 or original["calls"] != 0:
        raise ValueError("original-tool canary counters are invalid")


def _verify_early_exit(reduced: Capsule, tool: FunctionTool) -> None:
    async def early_exit(session: Any) -> Any:
        agent = Agent(
            name="RunSieve evidence application",
            instructions="Call probe once, then report the marker.",
            model=session.model,
            tools=list(session.tools),
            tool_use_behavior="stop_on_first_tool",
        )
        return await session.run(agent, "find failure")

    try:
        _run(OpenAIAgentsReplaySession(reduced, original_tools=(tool,)).execute(early_exit))
    except ApplicationReplayDivergence as exc:
        if "unconsumed" not in str(exc):
            raise ValueError(f"unexpected early-exit divergence: {exc}") from exc
    else:
        raise ValueError("early application exit did not diverge")


def _verify_unsupported_surface(reduced: Capsule, tool: FunctionTool) -> None:
    replay = reduced.metadata.get("application_replay")
    if not isinstance(replay, dict):
        raise ValueError("application replay metadata is malformed")
    unsupported = replace(
        reduced,
        metadata={
            **reduced.metadata,
            "application_replay": {**replay, "protocol": "unsupported-protocol"},
        },
    )
    try:
        OpenAIAgentsReplaySession(unsupported, original_tools=(tool,))
    except ApplicationReplayUnsupported:
        return
    raise ValueError("unsupported application surface was accepted")


def _ordering_mutation(capsule: Capsule) -> Capsule:
    events = list(capsule.events)
    requests = [index for index, event in enumerate(events) if event.kind == "model_request"]
    if len(requests) != 2:
        raise ValueError("application replay ordering fixture must have two model requests")
    first, second = requests
    first_event, second_event = events[first], events[second]
    events[first] = replace(first_event, payload=second_event.payload)
    events[second] = replace(second_event, payload=first_event.payload)
    return replace(capsule, events=tuple(events))


def _verify_minimality(reduced: Capsule) -> None:
    tool = _tool({"calls": 0})

    def evaluate(candidate: Capsule) -> PredicateResult:
        try:
            report = _run(
                OpenAIAgentsReplaySession(
                    candidate,
                    original_tools=(tool,),
                ).execute(lambda session: _application(session, {"calls": 0}))
            )
        except ApplicationReplayDivergence:
            return PredicateResult.ABSENT
        except (ApplicationReplayUnsupported, ValueError):
            return PredicateResult.INVALID
        return (
            PredicateResult.REPRODUCES
            if report.final_output == "needle confirmed"
            else PredicateResult.ABSENT
        )

    proof = verify_one_minimal(reduced, evaluate)
    if not proof.is_one_minimal:
        raise ValueError("independent application replay minimality failed")


def verify_evidence(directory: Path, *, expected_commit: str) -> dict[str, Any]:
    if _SHA.fullmatch(expected_commit) is None:
        raise ValueError("expected application replay commit is invalid")
    root = ensure_real_directory(directory, label="application replay evidence directory")
    manifest_path = ensure_regular_file(
        root / "evidence.json",
        label="application replay evidence manifest",
    )
    manifest = _canonical_document(manifest_path, label="application replay evidence manifest")
    if (
        set(manifest) != {"artifacts", "commit", "gate", "producer", "schema_version"}
        or manifest.get("schema_version") != 1
        or manifest.get("gate") != "RS-05-AR1"
        or manifest.get("commit") != expected_commit
    ):
        raise ValueError("application replay evidence commit or identity is invalid")
    producer = manifest.get("producer")
    if (
        not isinstance(producer, dict)
        or set(producer) != {"bytes", "path", "sha256"}
        or producer.get("path") != "scripts/generate_application_replay_evidence.py"
    ):
        raise ValueError("application replay producer identity is invalid")
    producer_path = ensure_regular_file(
        ROOT / producer["path"],
        label="application replay producer",
    )
    if producer_path.stat().st_size != producer.get("bytes") or _sha256(producer_path) != producer.get("sha256"):
        raise ValueError("application replay producer identity differs from the evidence")
    artifacts = _artifact_paths(root, manifest)
    producer_report = _canonical_document(
        artifacts["producer-report"],
        label="application replay producer report",
    )
    if producer_report.get("commit") != expected_commit:
        raise ValueError("application replay producer report commit is invalid")
    source = load_capsule(artifacts["source-capsule"])
    reduced = load_capsule(artifacts["reduced-capsule"])
    if not source.workspace or reduced.workspace:
        raise ValueError("application replay evidence did not remove a real workspace unit")

    _verify_replay(reduced)
    tool = _tool({"calls": 0})
    instruction_mutation = _event_mutation(
        reduced,
        kind="model_request",
        field="system_instructions",
        value="Do not call any tool.",
    )
    _expect_divergence(
        instruction_mutation,
        tool=tool,
        pattern="model request",
    )
    input_mutation = _event_mutation(
        reduced,
        kind="model_request",
        field="input",
        value="different input",
    )
    _expect_divergence(input_mutation, tool=tool, pattern="model request")
    schema_mutation = _event_mutation(
        reduced,
        kind="model_request",
        field="tools",
        value=[],
    )
    _expect_divergence(schema_mutation, tool=tool, pattern="model request")
    argument_mutation = _event_mutation(
        reduced,
        kind="tool_call",
        field="arguments",
        value={"value": 8},
    )
    _expect_divergence(
        argument_mutation,
        tool=tool,
        pattern="tool arguments",
    )
    _expect_divergence(
        _ordering_mutation(reduced),
        tool=tool,
        pattern="model request",
    )
    _verify_early_exit(reduced, tool)
    _verify_unsupported_surface(reduced, tool)
    _verify_caught_original_attempt(reduced)
    _verify_minimality(reduced)

    return {
        "assertions": [
            {"id": assertion, "passed": True}
            for assertion in _ASSERTIONS
        ],
        "commit": expected_commit,
        "gate": "RS-05-AR1",
        "passed": True,
        "schema_version": 1,
    }


def write_verification_attestation(
    directory: Path,
    *,
    expected_commit: str,
    output: Path,
) -> dict[str, Any]:
    report = verify_evidence(directory, expected_commit=expected_commit)
    root = ensure_real_directory(directory, label="application replay evidence directory")
    target = output.resolve(strict=False)
    if target.parent.resolve(strict=True) != root:
        raise ValueError("application replay verification output must be inside its evidence directory")
    if target.exists() or target.is_symlink():
        raise FileExistsError("application replay verification output already exists")
    manifest_path = ensure_regular_file(
        root / "evidence.json",
        label="application replay evidence manifest",
    )
    verifier_path = Path(__file__).resolve()
    attestation: dict[str, Any] = {
        "assertions": report["assertions"],
        "commit": expected_commit,
        "evidence_manifest": {
            "bytes": manifest_path.stat().st_size,
            "path": manifest_path.name,
            "sha256": _sha256(manifest_path),
        },
        "gate": "RS-05-AR1",
        "passed": True,
        "schema_version": 1,
        "verifier": {
            "bytes": verifier_path.stat().st_size,
            "path": verifier_path.relative_to(ROOT).as_posix(),
            "sha256": _sha256(verifier_path),
        },
    }
    with target.open("xb") as stream:
        stream.write(canonical_json(attestation))
    return attestation


def _head(repo_root: Path = ROOT) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    commit = completed.stdout.strip()
    if completed.returncode or _SHA.fullmatch(commit) is None:
        raise ValueError("application replay verifier cannot resolve HEAD")
    return commit


def _require_head_blob(repo_root: Path, path: Path) -> None:
    try:
        relative = path.resolve(strict=True).relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise ValueError("application replay evidence path escapes its repository") from exc
    completed = subprocess.run(
        ["git", "cat-file", "blob", f"HEAD:{relative}"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise ValueError(f"application replay evidence path is not tracked in HEAD: {relative}")
    if completed.stdout != path.read_bytes():
        raise ValueError(f"application replay evidence path differs from HEAD: {relative}")


def verify_evidence_tracked_in_head(
    directory: Path,
    *,
    expected_commit: str,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    report = verify_evidence(directory, expected_commit=expected_commit)
    repository = ensure_real_directory(
        repo_root,
        label="application replay evidence repository",
    )
    head = _head(repository)
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", expected_commit, head],
        cwd=repository,
        capture_output=True,
        check=False,
    )
    if ancestry.returncode:
        raise ValueError("application replay evidence commit is not an ancestor of HEAD")

    root = ensure_real_directory(directory, label="application replay evidence directory")
    manifest_path = ensure_regular_file(
        root / "evidence.json",
        label="application replay evidence manifest",
    )
    manifest = _canonical_document(manifest_path, label="application replay evidence manifest")
    artifacts = _artifact_paths(root, manifest)
    verification_path = ensure_regular_file(
        root / "verification.json",
        label="application replay verification attestation",
    )
    verification = _canonical_document(
        verification_path,
        label="application replay verification attestation",
    )
    if (
        set(verification)
        != {
            "assertions",
            "commit",
            "evidence_manifest",
            "gate",
            "passed",
            "schema_version",
            "verifier",
        }
        or verification.get("schema_version") != 1
        or verification.get("gate") != "RS-05-AR1"
        or verification.get("commit") != expected_commit
        or verification.get("passed") is not True
        or verification.get("assertions") != report["assertions"]
    ):
        raise ValueError("application replay verification attestation is invalid")
    manifest_identity = verification.get("evidence_manifest")
    if (
        not isinstance(manifest_identity, dict)
        or set(manifest_identity) != {"bytes", "path", "sha256"}
        or manifest_identity.get("path") != "evidence.json"
        or manifest_identity.get("bytes") != manifest_path.stat().st_size
        or manifest_identity.get("sha256") != _sha256(manifest_path)
    ):
        raise ValueError("application replay evidence manifest attestation is invalid")

    producer = cast(dict[str, Any], manifest["producer"])
    producer_path = ensure_regular_file(
        repository / producer["path"],
        label="application replay evidence producer",
    )
    verifier = verification.get("verifier")
    if (
        not isinstance(verifier, dict)
        or set(verifier) != {"bytes", "path", "sha256"}
        or not isinstance(verifier.get("path"), str)
    ):
        raise ValueError("application replay evidence verifier identity is invalid")
    safe_relative_path(
        verifier["path"],
        label="application replay evidence verifier",
    )
    verifier_path = ensure_regular_file(
        repository / verifier["path"],
        label="application replay evidence verifier",
    )
    if (
        verifier_path.stat().st_size != verifier.get("bytes")
        or _sha256(verifier_path) != verifier.get("sha256")
    ):
        raise ValueError("application replay evidence verifier differs from the attestation")

    for path in (
        manifest_path,
        verification_path,
        producer_path,
        verifier_path,
        *artifacts.values(),
    ):
        _require_head_blob(repository, path)
    return report


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    output: Path | None = None
    require_tracked = False
    if "--require-tracked" in arguments:
        arguments.remove("--require-tracked")
        require_tracked = True
    if "--output" in arguments:
        index = arguments.index("--output")
        if index + 1 >= len(arguments):
            print("application replay verifier --output needs a path", file=sys.stderr)
            return 2
        output = Path(arguments[index + 1])
        del arguments[index : index + 2]
    if output is not None and require_tracked:
        print(
            "application replay verifier cannot combine --output and --require-tracked",
            file=sys.stderr,
        )
        return 2
    if len(arguments) not in {1, 2}:
        print(
            "usage: python -m scripts.verify_application_replay_evidence "
            "EVIDENCE_DIR [EXPECTED_COMMIT] "
            "[--output ATTESTATION | --require-tracked]",
            file=sys.stderr,
        )
        return 2
    try:
        expected_commit = arguments[1] if len(arguments) == 2 else _head()
        report = (
            verify_evidence_tracked_in_head(
                Path(arguments[0]),
                expected_commit=expected_commit,
            )
            if require_tracked
            else (
                write_verification_attestation(
                    Path(arguments[0]),
                    expected_commit=expected_commit,
                    output=output,
                )
                if output is not None
                else verify_evidence(
                    Path(arguments[0]),
                    expected_commit=expected_commit,
                )
            )
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"application replay evidence verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
