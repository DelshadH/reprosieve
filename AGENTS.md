# Repository instructions

## Goal

Build RunSieve into a dependable command-line tool that turns one failed agent
run into a smaller, redacted, deterministic reproduction that works offline.
Keep the promise narrow and falsifiable; do not turn it into an observability
platform or generic trace viewer.

## Read first

1. `README.md`
2. `docs/product.md`
3. `docs/privacy.md`
4. `docs/architecture.md`
5. `docs/quality-plan.md`

## Commands

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
python -m mypy
python -m build
```

Support Python 3.11 through 3.13. Keep the minimization core standard-library
first and the public schema versioned.

## Working rules

- Build end-to-end slices: capture or load a capsule, run the predicate, reduce,
  verify minimality, and export a reproduction. A disconnected helper is not a
  finished feature.
- Start behavior changes with a failing test. Include invalid, timeout, signal,
  limit, cancellation, and malformed-input cases where relevant.
- Preserve the tri-state predicate. Invalid candidates are never equivalent to
  “failure absent” and can never be accepted as successful reductions.
- Keep source capsules immutable. A reduction produces a new hash-addressed
  artifact and records the exact predicate and environment.
- Report 1-minimality precisely; never claim a global minimum.
- Use plain technical prose. Avoid filler, speculative diagnosis, and claims not
  backed by a reproducible fixture.
- Do not weaken a test, resource limit, privacy invariant, or release requirement
  merely to make CI pass.

## Security and privacy boundaries

- Treat traces, archives, commands, paths, captured files, and predicates as
  untrusted input.
- Redact before bytes can reach disk, logs, exceptions, temporary archives, or
  telemetry. Byte-scan all produced artifacts with secret canaries in tests.
- Reject archive traversal, symlink escapes, duplicate members, oversized input,
  decompression bombs, invalid references, and unsupported schema versions.
- Run predicates with direct argument vectors where possible, a minimal
  environment, clean temporary directories, time/output/process limits, and
  outbound network denial for offline proofs.
- Offline replay must not call providers or original external tools. Tests should
  fail loudly if either boundary is crossed.
- Review every new dependency for necessity, maintenance, license, install-time
  behavior, and known vulnerabilities.

## Completion standard

A feature is complete only when the real CLI path works from a clean checkout,
tests cover its failure modes, public docs match behavior, and the corresponding
requirement in `docs/quality-plan.md` has reproducible evidence. Before release,
run the complete Python matrix, package smoke tests, dependency and secret scans,
hostile archive/capsule tests, privacy canaries, and the clean-room demo.
