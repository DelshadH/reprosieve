# Product contract

## Canonical 0.1 promise

Given one valid failed-agent-run capsule and a declared Python failure predicate, RunSieve produces a smaller redacted capsule such that deterministic materialization of its retained recorded values still causes the predicate to report the target failure in a fresh constrained trial, and deleting any remaining declared final-granularity unit makes the predicate report the failure absent or makes the candidate invalid.

## Primary user

An agent framework maintainer or coding agent that needs to attach a compact, portable recorded-trajectory reduction to an issue or regression test.

## Exact product identities

### Trace reduction

Remove declared events, fields, messages, files, and other units while preserving schema validity, graph validity, parent and dependency integrity, the declared predicate result, and declared reduction semantics.

### Recorded-output materialization

Walk the retained event graph and deterministically emit its recorded model and tool values. Materialization does not execute application or orchestration code, call a provider or original tool, or prove that a model would produce the trajectory again.

### Offline predicate reproduction

Execute only the declared predicate against the retained capsule and materialized recorded values in fresh constrained trials. This can establish that the declared failure recognizer reports `reproduces`; it is not application replay and does not establish that the original application, provider, tool, SDK behavior, or serialization path executed again.

### Application replay

Rerun a declared application or orchestration entry point while substituting recorded provider and tool interactions through a framework-specific public adapter. Application replay is outside the 0.1 contract. A later 0.5 claim requires measured application execution, strict interaction matching, divergence detection, and canaries proving that live providers and original tools were not invoked.

## 0.1 capture

The OpenAI Agents SDK adapter records through its public tracing processor interface. By default it installs with `set_trace_processors()` and replaces the SDK default exporter; using `add_trace_processor()` or retaining another exporter requires explicit user opt-in:

- trace/span topology and stable local IDs;
- model inputs and captured model outputs needed for reduction and materialization;
- tool names, JSON-safe arguments, captured results/errors, and call dependencies;
- handoff/guardrail events represented by the SDK trace;
- run configuration relevant to the declared predicate;
- declared workspace files and environment-key allowlist;
- runtime/package fingerprint.

Secrets are redacted in memory before RunSieve's own first persistence. Raw provider payloads outside the explicit schema are not silently stored.

## Reduction units and minimality

Apply the dependency-preserving hierarchy:

1. independent trace branches/spans;
2. turns/messages;
3. model request/response and tool-call/result pairs;
4. JSON object fields and array elements;
5. text chunks;
6. declared workspace files and file chunks;
7. allowed environment entries.

After each accepted reduction, restart the current hierarchy level. A completed result is 1-minimal under the declared final-granularity units: deleting any remaining such unit makes the predicate report the target failure absent or makes the candidate invalid. This is not a global-minimum claim.

## Predicate protocol

Run the predicate in a fresh temporary directory with the capsule path and materialized-value path in documented environment variables.

- exit `0`: the target failure is reproduced;
- exit `1`: target failure is absent;
- exit `2`: invalid candidate or predicate harness failure;
- timeout, signal, malformed result: invalid.

K-of-N in 0.1 repeats only the declared predicate in fresh trials. Store every trial result and label the result probabilistic. It does not make live model calls.

## Operating boundary

The 0.1 proof boundary is the documented Python runner and its child-process controls: minimal environment, fresh directory, direct argument vector, filesystem policy, output/time/process limits, and outbound-network denial where the platform proof supports it. Python audit hooks are defense-in-depth, not a universal sandbox. Capsule-supplied commands or entry points never execute silently.

## Capsule

A `.runsieve` file is a deterministic ZIP with normalized timestamps/order and contains `manifest.json`, versioned events, redaction report, environment fingerprint, declared materialization assets, predicate metadata, and SHA-256 hashes. It must not include credentials, provider API keys, or undeclared workspace files.

## Non-goals

RunSieve 0.1 does not claim a global minimum, application replay, live model replay, semantic model reproduction, root-cause diagnosis, complete privacy detection, arbitrary-code sandboxing, support for arbitrary side effects, or proof that the original failure would recur in a new live run.
