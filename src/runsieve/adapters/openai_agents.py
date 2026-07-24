from __future__ import annotations

from typing import Any


class RunSieveTraceProcessor:
    """Pre-release adapter for the OpenAI Agents SDK tracing processor protocol.

    The complete adapter will convert incoming public trace/span objects into
    bounded RunSieve records and redact them in memory before persistence.
    """

    def on_trace_start(self, trace: Any) -> None:
        raise NotImplementedError("capture is not available in this pre-release build")

    def on_trace_end(self, trace: Any) -> None:
        raise NotImplementedError("capture is not available in this pre-release build")

    def on_span_start(self, span: Any) -> None:
        raise NotImplementedError("capture is not available in this pre-release build")

    def on_span_end(self, span: Any) -> None:
        raise NotImplementedError("capture is not available in this pre-release build")

    def shutdown(self) -> None:
        return None

    def force_flush(self) -> None:
        return None
