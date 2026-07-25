# Canonical-history migration plan

## Discovered topology

- Public default `main` points to the original implementation lineage rooted at
  `c373468816973584b03784b8114c257bdac52dd9`.
- The contract skeleton lineage is rooted at
  `d8585c707dcc6413e9fb5bb33212342918837163`.
- Corrected contract v2 is an unrelated one-root lineage at
  `8686965f35a6521400e404891a72fb5d8dc3471d` on `contract-v2-main`.
- Draft pull request 3 targets `contract-main` from
  `codex/contract-migration`; it remains the unchanged contract-v1 audit
  history.

## Preserved refs

- `archive/pre-contract-migration-main-20260725` preserves the former public
  `main` lineage.
- `codex/safety-contract-migration-20260725` preserves migration commit
  `c0b0b249295bdaf2299fb02ee0e8c487289cdb06`.

These refs must not be force-moved or deleted during migration.

## Safe sequence

1. Complete implementation and evidence on `codex/contract-v2-migration`,
   based only on `contract-v2-main`.
2. Require green CI and a green release gate on the exact replacement commit.
3. Review the v1/v2 immutable diff, port allowlist, full history, and file
   delta; keep pull request 3 unchanged and draft.
4. Review a separate contract-v2 migration PR targeting `contract-v2-main`.
5. A repository owner updates the default branch to the reviewed contract
   lineage without force-pushing either lineage.
6. Update branch protection, required checks, contribution links, issue forms,
   and any external links to the selected canonical branch.
7. Fresh-clone the public URL into an empty directory and run install, tests,
   public CLI flows, and the release gate without local-only refs.
8. Close or supersede obsolete migration PRs only after linking the accepted
   contract-v2 replacement and archival refs.

Changing the GitHub default branch and protected settings is a human-owner
action. It remains a manual release blocker; it is not assumed complete by a
local test.
