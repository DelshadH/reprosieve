# Product contract

## One-sentence promise

Given one failed agent-run capsule and an executable failure predicate, RunSieve produces a smaller redacted capsule that reproduces the same failure offline and is 1-minimal under declared reduction units.

## Primary user

An agent framework maintainer or coding agent that needs to attach a compact, portable failure reproduction to an issue or regression test.

## v0.1 capture

The OpenAI Agents SDK adapter records through its public tracing processor interface. By default it installs with `set_trace_processors()` and replaces the SDK default exporter; using `add_trace_processor()` or retaining another exporter requires explicit user opt-in:

- trace/span topology and stable local IDs;
- model inputs and captured model outputs needed for replay;
- tool names, JSON-safe arguments, captured results/errors, and call dependencies;
- handoff/guardrail events represented by the SDK trace;
- run configuration that affects replay;
- declared workspace files and environment-key allowlist;
- runtime/package fingerprint.

Secrets are redacted in memory before persistence. Raw provider payloads outside the explicit schema are not silently stored.

## Recorded outputs and application replay

`runsieve replay` deterministically materializes retained model and tool outputs
as JSON. It does not execute application or orchestration code.

A capsule may declare an embedded `runsieve-recorded-v1` application adapter.
Predicate trials and the standalone reproduction execute that adapter first,
with model and tool interfaces backed only by the recorded trajectory. This can
reproduce application, orchestration, serialization, and tool-protocol failures
under one fixed trajectory. It does not prove that a model would generate the
trajectory again.

K-of-N mode repeats the same offline predicate in fresh directories and records
every attempt. It is labeled probabilistic, but it does not call a provider.
Live model replay is outside the pre-0.1 release.

## Reduction units

Apply in dependency-preserving hierarchy:

1. independent trace branches/spans;
2. turns/messages;
3. tool-call/result pairs;
4. JSON object fields and array elements;
5. text chunks;
6. declared workspace files and file chunks;
7. allowed environment entries.

After each accepted reduction, restart the current hierarchy level. A completed result is 1-minimal: deleting any remaining unit at the final granularity either removes the target failure or makes the candidate invalid.

## Predicate protocol

Run the predicate in an isolated temporary directory with capsule path and replay metadata in documented environment variables.

- exit `0`: the target failure is reproduced;
- exit `1`: target failure is absent;
- exit `2`: invalid candidate/harness failure;
- timeout, signal, malformed result: invalid.

For K-of-N, each trial uses a fresh directory. Store every trial result.

## Capsule

A `.runsieve` file is a deterministic ZIP with normalized timestamps/order and contains `manifest.json`, versioned events, redaction report, environment fingerprint, replay assets, predicate metadata, and SHA-256 hashes. The archive must never include credentials, provider API keys, or undeclared workspace files.

## Non-goals

RunSieve does not diagnose root cause, guarantee global minimum, guarantee a probabilistic model failure, replace an observability backend, or make arbitrary side-effecting tools hermetic.
