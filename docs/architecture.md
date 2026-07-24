# Architecture

## Modules

- `schema.py`: versioned immutable records and referential-integrity validation.
- `redact.py`: in-memory recursive redaction and canary detection.
- `adapters/openai_agents.py`: custom trace processor and capture lifecycle.
- `capsule.py`: deterministic archive read/write and hash manifest.
- `replay.py`: offline response/tool substitution and isolation.
- `predicate.py`: timeout-safe tri-state and K-of-N runner.
- `ddmin.py`: generic 1-minimal delta-debugging kernel.
- `hierarchy.py`: dependency-aware reduction units and repair/validation.
- `export.py`: clean repro directory and optional static viewer.
- `cli.py`: stable command/exit contract.

## Capture boundary

The capture bootstrap installs a RunSieve processor before the target entrypoint and replaces the default SDK trace processors unless the user explicitly opts into additional exporters. The adapter converts SDK trace objects into RunSieve's own versioned schema immediately. Internal provider/SDK object serialization must not leak into the capsule contract. Unknown span types are represented explicitly and block reductions that would misrepresent them. If the target program replaces processors after bootstrap or required span data is absent, capture exits as a harness failure rather than producing a partial capsule.

## Referential integrity

At minimum enforce:

- every child span references an existing parent or root;
- every tool result references exactly one retained tool call;
- every replayed model output maps to the retained request position;
- removing a producer removes or repairs dependent consumers as one candidate operation;
- IDs remain stable across candidates and are never recycled.

## Minimization algorithm

Use hierarchical ddmin with memoization by canonical candidate hash. The predicate cache key includes capsule hash, predicate hash, replay mode, environment hash, timeout, and probabilistic policy. Invalid results are not cached as absent failures when the cause is transient infrastructure.

After ddmin at each level, run a linear 1-minimality pass. Publish call counts and wall time; do not claim optimality.

## Isolation

Offline proofs run with no provider keys, an empty proxy configuration, denied outbound network where the platform permits, a clean temporary home, explicit environment allowlist, CPU/time/output limits, and copied-only declared files.
