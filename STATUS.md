# Status

- Contract-v2 root: anchored at
  `8686965f35a6521400e404891a72fb5d8dc3471d`.
- Canonical history: the reviewed PR 4-12 stack is merged. Public default
  `main` points to `ffabcab47d3c9fe05d3bbdc1ff8daca9a9485945`; the former
  lineage is preserved under recovery refs.
- Review: independent AI security, correctness, release, synthesis, and final
  adversarial passes are complete. No P0, P1, or release-blocking P2 remains.
- Evidence: canonical push CI run `30217885613` passed the Python 3.11-3.13,
  security, Linux/macOS, application replay, RS-G10, and RS-G13 matrix.
- Application replay: the public-API adapter is experimental 0.5 mechanics and
  remains outside the narrow 0.1 CLI promise.
- Publication: no tag, GitHub release, or registry upload is authorized until
  the owner answers the final `PUBLISH? YES / NO` decision.
- Registry: trusted-publisher credentials are not connected.
  `REGISTRY AUTHENTICATION UNAVAILABLE`.
- PR 3: preserved unchanged as superseded contract-v1 audit history.

Run `python -m scripts.verify` and `python -m scripts.final_release_gate`.
The exact-head final-evidence workflow is the current release receipt;
`scripts.release_gate` remains the immutable historical contract-v2 verifier.
