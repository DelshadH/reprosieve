# Status

- Contract-v2 root: anchored at
  `8686965f35a6521400e404891a72fb5d8dc3471d`.
- Canonical history: the reviewed PR 4-13 stack is merged. Public default
  `main` points to `13a8c3e9d8c614708678f943467f16f3a7418a66`; the former
  lineage is preserved under recovery refs.
- Review: independent AI security, correctness, release, synthesis, and final
  adversarial passes are complete. No P0, P1, or release-blocking P2 remains.
- Evidence: canonical push CI run `30219274054` and CodeQL run `30219274104`
  passed at `13a8c3e9d8c614708678f943467f16f3a7418a66`.
- Naming: the final collision check found an active, exact RunSieve /
  `runsieve` product, distribution, module, and CLI collision. The unpublished
  public release surface is being renamed to ReproSieve / `reprosieve`; the
  immutable contract-v2 audit lineage remains identified as `runsieve`.
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
