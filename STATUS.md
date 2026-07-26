# Status

- Contract-v2 root: anchored at `8686965f35a6521400e404891a72fb5d8dc3471d`.
- Accepted contract-v1 implementation: ported through the audited mutable-path allowlist.
- Candidate work: security, determinism, minimality-oracle, package, provenance,
  and publication-workflow remediations are being validated on
  `codex/autonomous-0.1.0a1-rc`.
- Last local verification: 140 tests plus 5 subtests, Ruff, and strict mypy
  passed before the release-engineering changes.
- Evidence: historical contract-v2 evidence remains immutable. A separate
  exact-head, attestation-bound final workflow will produce current Linux,
  macOS, Python 3.11–3.13, package, replay, and release-gate evidence.
- Application replay: the public-API adapter is experimental 0.5 mechanics and
  remains outside the narrow 0.1 CLI promise.
- Publication: no tag, GitHub release, or registry upload is authorized until
  the owner answers the final `PUBLISH? YES / NO` decision.
- PR #3: preserved unchanged as the contract-v1 audit history.

Run `python -m scripts.verify`; after the candidate is committed, use
`python -m scripts.final_release_gate` and the exact-head final-evidence
workflow as the current technical truth tests. `scripts.release_gate` remains
the immutable historical contract-v2 evidence verifier.
