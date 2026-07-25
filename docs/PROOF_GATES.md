# Proof gates

| Gate | Required proof | Release condition |
|---|---|---|
| RS-G13 | Clean Python package bootstrap | Fresh Linux environments build wheel/sdist, install, verify, and smoke-test the CLI on Python 3.11, 3.12, and 3.13. |
| RS-G01 | Official-adapter capture | A synthetic OpenAI Agents SDK run is captured through a public custom trace processor, with the default exporter replaced, and converted without SDK-private imports; a canary exporter proves no duplicate backend export occurs. |
| RS-G02 | Before-disk redaction | Injected canaries across all field classes are absent byte-for-byte from files, archives, stdout/stderr, and exception text. |
| RS-G03 | Deterministic capsule | Repeated builds from equal normalized input produce the same SHA-256; archive validates hashes and rejects traversal/bombs/malformed references. |
| RS-G04 | Offline hermetic replay | Captured failure reproduces with provider keys absent and outbound network denied; no model or original external tool is called. |
| RS-G05 | Meaningful reduction | Published 247-event fixture reduces to at most 10 events while preserving the exact predicate and referential integrity. |
| RS-G06 | 1-minimality | Independent verifier attempts to remove each remaining final-granularity unit; every attempt is absent or invalid for a documented structural reason. |
| RS-G07 | Tri-state correctness | Reproduces/absent/invalid/timeout/signal cases are distinct; invalid candidates can never be accepted as reductions. |
| RS-G08 | Hierarchical dependency reduction | Span, message, paired tool call/result, JSON field, text chunk, file, and environment reducers each have a real accepted reduction fixture. |
| RS-G09 | Probabilistic mode | Seeded flaky fixture validates K-of-N bookkeeping, fresh trial isolation, cache key, and complete attempt report; UI labels mode probabilistic. |
| RS-G10 | Clean issue capsule | Exported repro runs from a fresh temp directory on Linux and macOS with one command and no source repository or API key. |
| RS-G11 | Resource bounds | Timeouts, output caps, event caps, archive limits, recursion limits, and cancellation are tested under adversarial input. |
| RS-G12 | Release experience | Clean checkout installs, tests, minimizes the killer fixture, exports repro, verifies 1-minimality, and generates a ≤20-second terminal demo. |

`GATE_REGISTRY.json` fixes the machine-readable assertion IDs each verifier and manifest must contain. The release gate requires every registered gate. A tiny synthetic ddmin list test is not RS-G05 or RS-G06.
