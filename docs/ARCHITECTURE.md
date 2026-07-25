# Architecture

## Modules

- `schema.py`: immutable versioned records, bounded JSON, safe names, and graph validation.
- `redact.py`: in-memory recursive redaction and replacement reports.
- `safeio.py`: regular-file and no-symlink/junction path checks.
- `adapters/openai_agents.py`: public SDK processor and trace conversion.
- `_capture_bootstrap.py`: validated child-process processor installation.
- `capsule.py`: deterministic archive writing, hostile archive reading, and hash verification.
- `replay.py`: recorded-output materialization and the declared application-adapter protocol.
- `predicate.py`: isolated tri-state and K-of-N execution.
- `ddmin.py`: generic tri-state delta debugging.
- `hierarchy.py`: dependency-aware hierarchical reduction and memoization.
- `verify.py`: independent final-granularity 1-minimality proof.
- `export.py`: standalone issue reproduction.
- `cli.py`: command and exit contract.

## Capture

`runsieve capture` starts the target with a temporary `sitecustomize.py`. The
bootstrap imports only public `agents` and `agents.tracing` surfaces and installs
one `RunSieveTraceProcessor`. The target command is an argument vector; no shell
parsing is used.

Trace and span callbacks are synchronous and thread-safe. Span start order is
recorded, completed exports are redacted immediately, and event construction
waits for trace end. Generation and response spans become request/response
pairs. Function spans become call/result pairs. Sibling model and tool spans are
linked into a recorded trajectory within their parent scope.

## Referential integrity

Validation enforces:

- unique bounded event IDs and strictly increasing sequence numbers;
- parents and dependencies reference earlier retained events;
- each model response has exactly one model request producer;
- each tool result has exactly one tool call producer;
- workspace paths are normalized relative paths;
- environment names and all JSON values are bounded.

Deleting a producer recursively deletes consumers. IDs are never recycled;
sequence numbers alone are normalized.

## Minimization

Each level uses tri-state evaluation and canonical capsule hashes. Bulk event,
file, and environment levels use delta debugging. JSON units use restart-on-
accept greedy deletion. Text and file contents use fixed 32-character chunks.
Only `REPRODUCES` accepts a candidate. Invalid results remain invalid.

The cache key used by executable predicates includes the complete capsule bytes,
argument vector, timeout, output limit, process limit, K-of-N policy, environment,
and offline mode. Runtime call counts and wall time are printed; wall time is not
stored in deterministic capsule bytes.

The verifier is separate code and does not share the reducer's cache. It attempts
each retained event, JSON field/item, text chunk, file/chunk, and environment
entry exactly once.

## Isolation

Every Python predicate trial receives a fresh temporary home and only declared
files. The runner removes provider credentials, empties proxy variables,
discards predicate output after hashing it, and enforces timeout, output, file,
CPU, descriptor, and process limits where the platform exposes them.

`sitecustomize.py` patches network entry points and installs a Python audit hook
that denies host-file access, child processes, native loading, and destructive
operations outside the trial directory. This is meaningful defense in depth,
not an operating-system or virtual-machine sandbox; see the residual risks in
`docs/security-review.md`.

When `metadata.application_replay` declares `runsieve-recorded-v1`, the isolated
trial first runs the embedded application entry point. A generated standard-
library adapter supplies recorded model and tool outputs in trajectory order.
The entry point writes bounded JSON to `RUNSIEVE_APPLICATION_RESULT`; only then
does the predicate run. Without that declaration, `runsieve replay` and
predicate setup only materialize recorded outputs and make no application-replay
claim.
