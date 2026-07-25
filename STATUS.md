# Status

- Product state: pre-0.1 development build; not a release candidate.
- Capture, recorded-output materialization, offline predicate reproduction, reduction, independent
  1-minimality verification, and standalone export are implemented end to end.
- Gate verifiers consume hashed command output and gate-specific proof. Linux,
  macOS, Python 3.11-3.13, package, privacy, and security jobs run in CI.
- Real credentials, private source, personal data, and arbitrary production
  traces remain outside the safety claim.
- Application replay is deferred, zero real case studies are publishable, and
  the root-anchored final-state self-test contradiction keeps every control-plane
  task and gate pending.

Run `python -m scripts.verify`, the checks in `docs/quality-plan.md`, and finally
`python -m scripts.release_gate`. A public release is permitted only when that
last command exits successfully from a clean commit.
