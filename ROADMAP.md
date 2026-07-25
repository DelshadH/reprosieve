# Roadmap and maturity

## 0.1: honest reduction

- trace capture and dependency-aware reduction;
- deterministic recorded-output materialization;
- offline predicate reproduction in fresh constrained trials;
- independent 1-minimality evidence;
- Python 3.11–3.13 and Linux/macOS proof artifacts.

Application replay and real-world impact are not 0.1 claims.

## 0.5: replay-backed field evidence

- several permissioned real reductions;
- one framework-specific application replay adapter;
- strict request/order matching, measured interceptions, and divergence reports;
- published format compatibility experience.

## 1.0: durable public contract

- stable CLI and formats with defined deprecation windows;
- independently verified minimality over supported surfaces;
- sustained cross-platform evidence;
- reliable application replay;
- multiple active maintainers and sustained external use.

The 0.1 candidate has green exact-head and fresh-clone evidence and is ready
for independent alpha review. Canonical-history owner actions in
`docs/migration-plan.md` remain pending. Experimental 0.5 application replay
has a green independent synthetic gate at PR #7, but still needs permissioned
real-case evidence and independent human review. All three real-case categories
remain explicit external blockers; their package schema and structural verifier
do not substitute for cases, permissions, or sustained external use.

The exact evidence and blocker split is recorded in the canonical
[`docs/maturity-status.json`](docs/maturity-status.json) ledger.
The broader objective-by-objective proof and blocker audit is
[`docs/completion-audit.json`](docs/completion-audit.json).
The current-tree review of every non-negotiable evidence principle is
[`docs/principles-audit.json`](docs/principles-audit.json).
