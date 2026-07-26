# Status

- Contract-v2 root: anchored at `8686965f35a6521400e404891a72fb5d8dc3471d`.
- Accepted contract-v1 implementation: ported through the audited mutable-path allowlist.
- Local verification: contract-v2 self-tests, 96 tests plus 2 subtests, Ruff, and strict mypy pass before the port commit.
- Evidence: intentionally empty; every task and gate remains pending until clean contract-v2 commit evidence is generated.
- Application replay: unsupported and explicitly deferred beyond the 0.1 contract.
- Release gate: expected red while task and gate state is pending.
- PR #3: preserved unchanged as the contract-v1 audit history.

Run `python -m scripts.verify`; after implementation is committed and evidence is generated, use `python -m scripts.release_gate` as the final truth test.
