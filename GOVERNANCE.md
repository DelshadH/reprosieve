# Governance

ReproSieve is currently maintained through reviewed GitHub pull requests. The
repository owner is the final decision maker while the project has fewer than
two active maintainers.

Changes to the public capsule format, predicate protocol, minimality definition,
privacy boundary, or release gates require:

1. a written architecture decision;
2. a pull request with reproducible compatibility and negative tests;
3. green required checks on the exact commit;
4. review by a maintainer who did not author the change when a second maintainer
   is available.

Security reports use private GitHub Security Advisories. Conduct is governed by
`CODE_OF_CONDUCT.md`. Maintainer succession and loss-of-access recovery are
documented in `docs/recovery.md`.

External validation follows
[`docs/external-validation.md`](docs/external-validation.md). A maintainer must
reproduce a report and record its exact evidence identity before it can support
a compatibility or maturity claim; usage reports are not self-authenticating.

Multiple active maintainers and sustained external use are explicit maturity
level 1.0 requirements; the project does not currently meet them. The
machine-readable status ledger is
[`docs/maturity-status.json`](docs/maturity-status.json).
