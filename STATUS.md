# Status

- Product state: pre-0.1 release candidate for synthetic or disposable inputs.
- Capture, recorded-interface application replay, reduction, independent
  1-minimality verification, and standalone export are implemented end to end.
- Gate verifiers consume hashed command output and gate-specific proof. Linux,
  macOS, Python 3.11-3.13, package, privacy, and security jobs run in CI.
- Real credentials, private source, personal data, and arbitrary production
  traces remain outside the safety claim.

Run `python -m scripts.verify`, the checks in `docs/quality-plan.md`, and finally
`python -m scripts.release_gate`. A public release is permitted only when that
last command exits successfully from a clean commit.
