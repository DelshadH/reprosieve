# Verified implementation sources

Reviewed on 2026-07-24:

- [OpenAI Agents SDK tracing guide](https://openai.github.io/openai-agents-python/tracing/)
- [OpenAI Agents SDK tracing reference](https://openai.github.io/openai-agents-python/ref/tracing/)
- [OpenAI Agents SDK 0.18.3 release](https://github.com/openai/openai-agents-python/releases/tag/v0.18.3)
- [openai-agents 0.18.3 on PyPI](https://pypi.org/project/openai-agents/0.18.3/)

The official guide states that `set_trace_processors()` replaces the default
processors, while `add_trace_processor()` keeps the OpenAI backend exporter.
The 0.18.3 public `TracingProcessor` interface has synchronous
`on_trace_start`, `on_trace_end`, `on_span_start`, `on_span_end`, `shutdown`,
and `force_flush` methods. ReproSieve supports `>=0.18.3,<0.19` and CI installs
0.18.3 as both the minimum and current release at review time.

ReproSieve does not claim record/replay novelty. Its narrow claim is automatic
dependency-aware reduction to a redacted, deterministic, offline, 1-minimal
failure capsule.
