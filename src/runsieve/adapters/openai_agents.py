from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import threading
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from ..capsule import write_capsule
from ..redact import (
    RedactionLimits,
    RedactionPolicy,
    RedactionReport,
    redact_with_report,
)
from ..safeio import ensure_real_directory, ensure_regular_file
from ..schema import Capsule, Event, JsonValue, safe_relative_path, validate_capsule

try:
    from agents.tracing import TracingProcessor as _TracingProcessor
except ImportError:  # The adapter remains importable when the optional SDK extra is absent.
    class _TracingProcessor:  # type: ignore[no-redef]
        pass


_MINIMUM_VERSION = (0, 18, 3)
_MAXIMUM_VERSION = (0, 19, 0)


@dataclass(slots=True)
class _ReportCounter:
    replacements: int = 0
    scanned_nodes: int = 0
    reasons: dict[str, int] = field(default_factory=dict)

    def add(self, report: RedactionReport) -> None:
        self.replacements += report.replacements
        self.scanned_nodes += report.scanned_nodes
        for reason, count in report.reasons.items():
            self.reasons[reason] = self.reasons.get(reason, 0) + count

    def to_json(self) -> dict[str, JsonValue]:
        return {
            "replacements": self.replacements,
            "reasons": dict(sorted(self.reasons.items())),
            "scanned_nodes": self.scanned_nodes,
        }


@dataclass(slots=True)
class _SpanRecord:
    source_id: str
    parent_source_id: str | None
    order: int
    exported: dict[str, JsonValue] | None = None


@dataclass(slots=True)
class _TraceState:
    source_id: str
    local_id: str
    policy: RedactionPolicy
    trace_payload: dict[str, JsonValue]
    report: _ReportCounter
    spans: dict[str, _SpanRecord] = field(default_factory=dict)
    next_order: int = 0
    failed: bool = False


def _version_tuple(value: str) -> tuple[int, int, int]:
    release = value.split("+", 1)[0].split("-", 1)[0]
    parts = release.split(".")
    if len(parts) < 3 or not all(part.isdigit() for part in parts[:3]):
        raise RuntimeError("unsupported OpenAI Agents SDK version format")
    return tuple(int(part) for part in parts[:3])  # type: ignore[return-value]


def ensure_supported_agents_version() -> str:
    try:
        installed = version("openai-agents")
    except PackageNotFoundError as error:
        raise RuntimeError("install RunSieve with the 'openai' extra to capture SDK runs") from error
    selected = _version_tuple(installed)
    if not _MINIMUM_VERSION <= selected < _MAXIMUM_VERSION:
        raise RuntimeError("installed OpenAI Agents SDK version is outside the supported range")
    return installed


def _required_text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} is missing")
    return value


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _parse_json_string(value: JsonValue) -> JsonValue:
    if not isinstance(value, str):
        return value
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, RecursionError):
        return value
    if parsed is None or isinstance(parsed, (bool, int, float, str, list, dict)):
        return parsed
    return value


class RunSieveTraceProcessor(_TracingProcessor):
    """Capture SDK traces through the public synchronous tracing processor API."""

    def __init__(
        self,
        *,
        output_path: str | Path | None = None,
        exact_canaries: tuple[str, ...] = (),
        patterns: tuple[str, ...] = (),
        allow_paths: tuple[str, ...] = (),
        deny_paths: tuple[str, ...] = (),
        workspace_root: str | Path | None = None,
        workspace_paths: tuple[str, ...] = (),
        environment_names: tuple[str, ...] = (),
        max_events: int = 10_000,
        max_depth: int = 64,
        max_nodes: int = 250_000,
        max_string_bytes: int = 4 * 1024 * 1024,
        max_workspace_bytes: int = 16 * 1024 * 1024,
    ) -> None:
        if max_events < 1 or max_events > 100_000:
            raise ValueError("capture event limit is invalid")
        self._output_path = Path(output_path) if output_path is not None else None
        self._exact_canaries = exact_canaries
        self._patterns = patterns
        self._allow_paths = allow_paths
        self._deny_paths = deny_paths
        self._workspace_root = ensure_real_directory(
            workspace_root if workspace_root is not None else Path.cwd(),
            label="workspace root",
        )
        self._workspace_paths = workspace_paths
        self._environment_names = environment_names
        self._max_events = max_events
        self._max_workspace_bytes = max_workspace_bytes
        self._redaction_limits = RedactionLimits(
            max_depth=max_depth,
            max_nodes=max_nodes,
            max_string_bytes=max_string_bytes,
        )
        self._lock = threading.RLock()
        self._traces: dict[str, _TraceState] = {}
        self._completed: list[Capsule] = []
        self._failure_reason: str | None = None

    @property
    def completed_capsules(self) -> tuple[Capsule, ...]:
        with self._lock:
            return tuple(self._completed)

    @property
    def failure_reason(self) -> str | None:
        with self._lock:
            return self._failure_reason

    def _fail(self, reason: str, state: _TraceState | None = None) -> None:
        self._failure_reason = reason
        if state is not None:
            state.failed = True

    def _redact(
        self,
        value: object,
        *,
        state: _TraceState,
    ) -> JsonValue:
        result, report = redact_with_report(value, policy=state.policy)
        state.report.add(report)
        return result

    def on_trace_start(self, trace: Any) -> None:
        with self._lock:
            try:
                source_id = _required_text(getattr(trace, "trace_id", None), label="trace ID")
                if source_id in self._traces:
                    self._fail("capture received a duplicate trace start")
                    return
                salt = os.urandom(32)
                policy = RedactionPolicy(
                    salt=salt,
                    exact_canaries=self._exact_canaries,
                    patterns=self._patterns,
                    allow_paths=self._allow_paths,
                    deny_paths=self._deny_paths,
                    limits=self._redaction_limits,
                )
                state = _TraceState(
                    source_id=source_id,
                    local_id=f"trace_{os.urandom(16).hex()}",
                    policy=policy,
                    trace_payload={},
                    report=_ReportCounter(),
                )
                payload = self._redact(
                    {
                        "workflow_name": getattr(trace, "workflow_name", None),
                        "group_id": getattr(trace, "group_id", None),
                        "metadata": getattr(trace, "metadata", None),
                    },
                    state=state,
                )
                if not isinstance(payload, dict):
                    raise ValueError("trace payload is invalid")
                state.trace_payload = payload
                self._traces[source_id] = state
            except ValueError as error:
                reason = (
                    "capture payload exceeded a configured limit"
                    if "limit" in str(error)
                    else "capture received malformed trace data"
                )
                self._fail(reason)
            except Exception:  # noqa: BLE001 - tracing processors must never disrupt an SDK run.
                self._fail("capture processor failed safely")

    def on_trace_end(self, trace: Any) -> None:
        with self._lock:
            try:
                source_id = _required_text(getattr(trace, "trace_id", None), label="trace ID")
                state = self._traces.pop(source_id, None)
                if state is None:
                    self._fail("capture received a trace end without a start")
                    return
                if state.failed:
                    return
                capsule = self._build_capsule(state)
                workspace = self._capture_workspace(state)
                environment = self._capture_environment(state)
                capsule = Capsule(
                    schema_version=capsule.schema_version,
                    trace_id=capsule.trace_id,
                    events=capsule.events,
                    metadata=capsule.metadata,
                    workspace=workspace,
                    environment=environment,
                )
                validate_capsule(capsule)
                if self._output_path is not None:
                    if self._completed:
                        self._fail("capture output supports exactly one completed trace", state)
                        return
                    write_capsule(
                        capsule,
                        self._output_path,
                        redaction_report=state.report.to_json(),
                    )
                self._completed.append(capsule)
            except ValueError as error:
                reason = (
                    "capture payload exceeded a configured limit"
                    if "limit" in str(error) or "size" in str(error)
                    else "capture received malformed trace data"
                )
                self._fail(reason)
            except (OSError, FileExistsError):
                self._fail("capture output could not be written safely")
            except Exception:  # noqa: BLE001 - tracing processors must never disrupt an SDK run.
                self._fail("capture processor failed safely")

    def on_span_start(self, span: Any) -> None:
        with self._lock:
            try:
                trace_id = _required_text(getattr(span, "trace_id", None), label="span trace ID")
                span_id = _required_text(getattr(span, "span_id", None), label="span ID")
                state = self._traces.get(trace_id)
                if state is None:
                    self._fail("capture received a span outside a trace")
                    return
                if span_id in state.spans:
                    self._fail("capture received a duplicate span", state)
                    return
                state.spans[span_id] = _SpanRecord(
                    source_id=span_id,
                    parent_source_id=_optional_text(getattr(span, "parent_id", None)),
                    order=state.next_order,
                )
                state.next_order += 1
                if state.next_order * 2 + 1 > self._max_events:
                    self._fail("capture payload exceeded a configured limit", state)
            except ValueError:
                self._fail("capture received malformed span data")
            except Exception:  # noqa: BLE001 - tracing processors must never disrupt an SDK run.
                self._fail("capture processor failed safely")

    def on_span_end(self, span: Any) -> None:
        with self._lock:
            try:
                trace_id = _required_text(getattr(span, "trace_id", None), label="span trace ID")
                span_id = _required_text(getattr(span, "span_id", None), label="span ID")
                state = self._traces.get(trace_id)
                if state is None:
                    self._fail("capture received a span outside a trace")
                    return
                record = state.spans.get(span_id)
                if record is None:
                    self._fail("capture received a span end without a start", state)
                    return
                exported = span.export()
                redacted = self._redact(exported, state=state)
                if not isinstance(redacted, dict):
                    raise ValueError("span export is invalid")
                record.exported = redacted
            except ValueError as error:
                reason = (
                    "capture payload exceeded a configured limit"
                    if "limit" in str(error)
                    else "capture received malformed span data"
                )
                state_value = locals().get("state")
                self._fail(reason, state_value if isinstance(state_value, _TraceState) else None)
            except Exception:  # noqa: BLE001 - tracing processors must never disrupt an SDK run.
                self._fail("capture processor failed safely")

    def shutdown(self) -> None:
        with self._lock:
            if self._traces:
                self._fail("capture ended with incomplete traces")
                self._traces.clear()

    def force_flush(self) -> None:
        return None

    def _add_event(
        self,
        events: list[Event],
        *,
        kind: str,
        parent_id: str,
        payload: JsonValue,
        dependencies: tuple[str, ...] = (),
    ) -> str:
        event_id = f"e{len(events):06d}"
        events.append(
            Event(
                id=event_id,
                kind=kind,  # type: ignore[arg-type]
                parent_id=parent_id,
                sequence=len(events),
                payload=payload,
                dependencies=dependencies,
            )
        )
        return event_id

    def _build_capsule(self, state: _TraceState) -> Capsule:
        events: list[Event] = [
            Event("e000000", "run", None, 0, state.trace_payload),
        ]
        tail_by_source: dict[str, str] = {}
        trajectory: dict[str, dict[str, str]] = {}
        for record in sorted(state.spans.values(), key=lambda item: item.order):
            if record.exported is None:
                raise ValueError("required span data is missing")
            if record.parent_source_id is None:
                parent_id = "e000000"
                scope = "root"
            else:
                parent_id = tail_by_source.get(record.parent_source_id, "")
                if not parent_id:
                    raise ValueError("span parent is missing or starts after its child")
                scope = record.parent_source_id
            exported = record.exported
            span_data = exported.get("span_data")
            if not isinstance(span_data, dict):
                raise ValueError("span data export is missing")
            span_type = span_data.get("type")
            error = exported.get("error")
            track = trajectory.setdefault(scope, {})
            if span_type in {"generation", "response"}:
                request_payload: dict[str, JsonValue] = {
                    "input": span_data.get("input"),
                }
                for key in ("model", "model_config"):
                    if key in span_data:
                        request_payload[key] = span_data[key]
                request_dependencies = (
                    (track["last_tool_result"],) if "last_tool_result" in track else ()
                )
                request_id = self._add_event(
                    events,
                    kind="model_request",
                    parent_id=parent_id,
                    payload=request_payload,
                    dependencies=request_dependencies,
                )
                output = span_data.get("output")
                if span_type == "response" and "response" in span_data:
                    output = span_data.get("response")
                response_payload: dict[str, JsonValue] = {
                    "output": output,
                    "usage": span_data.get("usage"),
                }
                if error is not None:
                    response_payload["error"] = error
                response_id = self._add_event(
                    events,
                    kind="model_response",
                    parent_id=parent_id,
                    payload=response_payload,
                    dependencies=(request_id,),
                )
                tail_by_source[record.source_id] = response_id
                track["last_model_response"] = response_id
            elif span_type == "function":
                call_payload: dict[str, JsonValue] = {
                    "arguments": _parse_json_string(span_data.get("input")),
                    "name": span_data.get("name"),
                }
                if "mcp_data" in span_data:
                    call_payload["mcp_data"] = span_data["mcp_data"]
                call_dependencies = (
                    (track["last_model_response"],) if "last_model_response" in track else ()
                )
                call_id = self._add_event(
                    events,
                    kind="tool_call",
                    parent_id=parent_id,
                    payload=call_payload,
                    dependencies=call_dependencies,
                )
                result_payload: dict[str, JsonValue] = {
                    "name": span_data.get("name"),
                    "output": _parse_json_string(span_data.get("output")),
                }
                if error is not None:
                    result_payload["error"] = error
                result_id = self._add_event(
                    events,
                    kind="tool_result",
                    parent_id=parent_id,
                    payload=result_payload,
                    dependencies=(call_id,),
                )
                tail_by_source[record.source_id] = result_id
                track["last_tool_result"] = result_id
            else:
                kind = {
                    "turn": "message",
                    "handoff": "handoff",
                    "guardrail": "guardrail",
                }.get(str(span_type), "error" if error is not None else "unknown")
                payload: dict[str, JsonValue] = {"span_data": span_data}
                if error is not None:
                    payload["error"] = error
                event_id = self._add_event(
                    events,
                    kind=kind,
                    parent_id=parent_id,
                    payload=payload,
                )
                tail_by_source[record.source_id] = event_id
        metadata: dict[str, JsonValue] = {
            "adapter": {
                "name": "openai-agents",
                "public_interface": "TracingProcessor",
                "version": ensure_supported_agents_version(),
            },
            "replay_mode": "offline",
            "runtime": {
                "implementation": platform.python_implementation(),
                "platform": sys.platform,
                "python": platform.python_version(),
            },
        }
        capsule = Capsule(
            schema_version="1",
            trace_id=state.local_id,
            events=tuple(events),
            metadata=metadata,
        )
        validate_capsule(capsule)
        return capsule

    def _safe_workspace_name(self, path: str, state: _TraceState) -> str:
        redacted = self._redact(path, state=state)
        if not isinstance(redacted, str):
            raise ValueError("workspace path redaction failed")
        if redacted == path:
            return path
        suffix = Path(path).suffix
        if len(suffix) > 16 or not suffix.replace(".", "").isalnum():
            suffix = ""
        digest = hashlib.sha256(state.policy.salt + path.encode("utf-8")).hexdigest()[:20]
        return f"redacted-{digest}{suffix}"

    def _capture_workspace(self, state: _TraceState) -> dict[str, str]:
        workspace: dict[str, str] = {}
        total = 0
        root = self._workspace_root
        if root.is_symlink() or not root.is_dir():
            raise ValueError("workspace root is not a real directory")
        for raw_path in self._workspace_paths:
            relative = safe_relative_path(raw_path, label="workspace path")
            resolved = ensure_regular_file(
                root / Path(relative),
                label="declared workspace path",
            )
            try:
                resolved.relative_to(root)
            except ValueError as error:
                raise ValueError("declared workspace path escapes its root") from error
            data = resolved.read_bytes()
            total += len(data)
            if total > self._max_workspace_bytes:
                raise ValueError("workspace size limit exceeded")
            try:
                content = data.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ValueError("declared workspace file is not UTF-8") from error
            safe_path = self._safe_workspace_name(relative, state)
            safe_relative_path(safe_path, label="workspace path")
            redacted = self._redact(content, state=state)
            if not isinstance(redacted, str):
                raise ValueError("workspace content redaction failed")
            if safe_path in workspace:
                raise ValueError("workspace path redaction collision")
            workspace[safe_path] = redacted
        return workspace

    def _capture_environment(self, state: _TraceState) -> dict[str, str]:
        captured: dict[str, str] = {}
        for name in self._environment_names:
            if not name or "\x00" in name:
                raise ValueError("environment allowlist entry is invalid")
            value = os.environ.get(name)
            if value is None:
                continue
            safe_name_value = self._redact(name, state=state)
            if not isinstance(safe_name_value, str):
                raise ValueError("environment name redaction failed")
            safe_name = safe_name_value
            if safe_name != name:
                digest = hashlib.sha256(state.policy.salt + name.encode()).hexdigest()[:16]
                safe_name = f"RUNSIEVE_REDACTED_{digest.upper()}"
            redacted = self._redact(value, state=state)
            if isinstance(redacted, str):
                safe_value = redacted
            elif isinstance(redacted, dict):
                fingerprint = redacted.get("fingerprint")
                safe_value = f"<redacted:{fingerprint}>"
            else:
                raise ValueError("environment value redaction failed")
            captured[safe_name] = safe_value
        return captured


def install_processor(
    processor: RunSieveTraceProcessor,
    *,
    retain_existing: bool = False,
) -> None:
    """Install through the SDK public API; replacement is the privacy-safe default."""
    ensure_supported_agents_version()
    try:
        from agents import add_trace_processor, set_trace_processors
    except ImportError as error:
        raise RuntimeError("OpenAI Agents SDK tracing API is unavailable") from error
    if retain_existing:
        add_trace_processor(processor)
    else:
        set_trace_processors([processor])
