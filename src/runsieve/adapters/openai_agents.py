from __future__ import annotations

from typing import Any


class RunSieveTraceProcessor:
    """RS-010 implementation target.

    Implement only against the OpenAI Agents SDK public tracing processor
    protocol. The capture bootstrap must install this with set_trace_processors()
    by default, replacing the SDK backend exporter; retaining other processors is
    an explicit opt-in. Convert incoming traces/spans immediately to RunSieve records,
    redact in memory, and enqueue bounded canonical events. Do not import SDK
    private modules or persist raw SDK objects.
    """

    def on_trace_start(self, trace: Any) -> None:
        raise NotImplementedError("execute CODEX task RS-010")

    def on_trace_end(self, trace: Any) -> None:
        raise NotImplementedError("execute CODEX task RS-010")

    def on_span_start(self, span: Any) -> None:
        raise NotImplementedError("execute CODEX task RS-010")

    def on_span_end(self, span: Any) -> None:
        raise NotImplementedError("execute CODEX task RS-010")

    def shutdown(self) -> None:
        return None

    def force_flush(self) -> None:
        return None
