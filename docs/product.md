# Product contract

## Promise

Given one failed agent-run capsule and an embedded Python failure predicate,
ReproSieve produces a smaller redacted capsule that reproduces the same failure
offline and is 1-minimal under declared reduction units.

The primary user is an agent framework maintainer who needs a compact issue
reproduction or regression fixture.

## Capture

The first adapter supports `openai-agents>=0.18.3,<0.19`. It implements the
public synchronous `TracingProcessor` callbacks and installs with
`set_trace_processors()` by default. That replaces the SDK backend exporter.
Keeping another exporter requires the explicit `--retain-sdk-exporter` option.

The adapter records:

- trace/span topology and stable capsule-local IDs;
- generation inputs and recorded outputs;
- tool names, JSON-safe arguments, results, errors, and trajectory dependencies;
- handoff, guardrail, turn, and unknown spans;
- declared UTF-8 workspace files and allowed environment entries;
- Python, platform, adapter, and SDK version information.

SDK objects are converted to bounded primitives and redacted in memory. Unknown
span types remain explicit. Missing parents, incomplete spans, excess events,
unsupported SDK versions, or more than one completed trace fail closed.

## Recorded values and predicate reproduction

`reprosieve materialize` walks the retained event graph and materializes recorded model
and tool outputs as deterministic JSON. That command does not execute
application or orchestration code.

`reprosieve reproduce-predicate` executes only the declared predicate against
those values in a fresh constrained directory. The exported `reproduce.py`
performs the same predicate reproduction without requiring ReproSieve or a source
checkout.

Application replay is not supported by the 0.1 CLI. An `application_replay`
declaration remains rejected by predicate and export paths. Experimental 0.5
library work has one OpenAI Agents adapter that reruns an explicit callback,
intercepts public provider and tool interfaces, enforces exact order and
arguments, measures canaries, and reports unused, extra, or divergent calls.
It remains synthetic-only and outside the 0.1 release claim; see
`application-replay.md`.

Predicates run in fresh directories with copied declared files, provider keys
removed, proxy variables emptied, direct argument vectors, time/output/process
limits, and Python audit hooks for network, process, native-loading, and
host-filesystem denial. These controls are defense in depth, not an OS sandbox;
embedded predicates remain arbitrary Python code. K-of-N runs use a fresh
directory for every trial and are
reported as probabilistic predicate evidence. They still use recorded outputs;
live model or application replay is outside the 0.1 seed release.

## Reduction units

The dependency-preserving hierarchy is:

1. independent spans and branches;
2. messages;
3. tool-call/result pairs;
4. JSON object fields;
5. JSON array elements;
6. text chunks;
7. declared workspace files;
8. file chunks;
9. allowed environment entries.

An accepted deletion restarts its level. Removing a producer also removes its
parent/dependency consumers. IDs are stable and sequence numbers are normalized.
After reduction, a separate verifier tries every remaining final-granularity
deletion without sharing the reducer cache.

## Capsule and export

A `.reprosieve` file is a deterministic ZIP with stored entries, normalized
timestamps/order/permissions, canonical JSON, a complete SHA-256 manifest, and:

- `events/v1.json`
- `metadata.json`
- `environment.json`
- `workspace/index.json`
- `workspace/files/*`
- `redaction.json`
- `predicate.json`

Source capsules are never overwritten. Reduced artifacts are named by the
SHA-256 of their complete bytes and record the source hash, predicate hash,
reduction evidence and an independent minimality proof. Construction-only mode
properties are not represented as measured call counters.

Export copies the exact capsule plus a standard-library `reproduce.py` and a
short README. `python reproduce.py --trust-embedded-predicate` validates all
hashes and safety limits, reconstructs recorded outputs, and runs the embedded
predicate. Without the explicit trust flag, it refuses execution.

## Non-goals

ReproSieve does not diagnose root cause, guarantee a global minimum, reproduce
model semantics, replace an observability backend, capture arbitrary processes,
support arbitrary predicate languages, or make side-effecting tools hermetic.
