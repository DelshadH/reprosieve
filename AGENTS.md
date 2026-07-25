# RunSieve agent contract

Act as principal engineer, failure-reduction researcher, privacy engineer, and adversarial user. Execute the task graph without waiting for routine decisions.

Read `docs/PRODUCT_CONTRACT.md`, `docs/ARCHITECTURE.md`, `docs/PRIVACY.md`, `docs/PROOF_GATES.md`, `docs/EVIDENCE.md`, `docs/CONTROL_PLANE.md`, `CODEX_TASKS.json`, `GATE_REGISTRY.json`, `PROGRESS.json`, `MANUAL_REQUIRED.json`, and `WORKLOG.md`; then follow `docs/AUTONOMOUS_LOOP.md`, `docs/RELEASE_STANDARD.md`, and `docs/EVIDENCE_CONTRACT.md`.


## Required control commands

Run `python -m scripts.bootstrap` once, before editing any file. Bootstrap commits the immutable execution clock into the root contract commit; never delete, reset, or recreate it. Use `python -m scripts.next_task` for task selection, `python -m scripts.verify` after each coherent change, and `python -m scripts.release_gate` only as the final truth test. `PROGRESS.json` cannot define the expected task/gate set; the graph and registry do. Gate verifiers begin as deliberate exit-64 placeholders and must be replaced by real, adversarial proof implementations—not constant-pass shims.

## Hard deadline

The v0.1 graph has a **72-hour elapsed execution window from bootstrap**. At a missed cumulative deadline, apply the task's kill/pivot rule immediately. Do not spend the deadline on a generic trace viewer, framework abstraction, or UI.

## Fixed choices

- Public name/executable/package: `RunSieve` / `runsieve` until a final collision check.
- Runtime: Python 3.11–3.13; core minimizer uses the standard library.
- First capture adapter: OpenAI Agents SDK through its public custom tracing processor surface. Default capture replaces the SDK default exporter with `set_trace_processors()` so captured data is not also exported elsewhere.
- Captured tools: JSON-safe request/response payloads only.
- Default mode: offline structural replay with no network and no API key.
- Reduction: dependency-aware hierarchical ddmin; invalid candidates never count as “failure absent.”
- Capsule: deterministic, versioned, redacted before persistence, issue-attachable.
- UI: generated static before/after HTML only after the CLI proof; no server.
- License: Apache-2.0.

## Forbidden before RS-G08 passes

Multiple agent frameworks, generic observability backend, hosted trace storage, browser application, MCP proxy, prompt optimizer, automated root-cause prose, distributed minimization, or proprietary trace formats.

## Truth rules

- “Minimal” means 1-minimal under the declared reduction units and predicate, not globally smallest.
- Offline replay must not call a model provider or original external tool.
- Redaction happens before bytes reach disk, including debug logs and failed writes.
- A candidate that breaks trace referential integrity is `invalid`, not a successful reduction.
- K-of-N live predicates report seeds, model identifier, parameters, attempts, and confidence policy; never describe them as deterministic.
- Keep the original capsule immutable; every reduction derives a new hash-addressed capsule.

## Manual work

Only authenticated GitHub/PyPI publication, registry 2FA/token, protected settings, legal identity, or paid API execution may require the user. Record exact instructions in `MANUAL_REQUIRED.json` and continue offline work.
