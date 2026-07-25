# Canonical-history migration plan

## Discovered topology

- Public default `main` points to the original implementation lineage rooted at
  `c373468816973584b03784b8114c257bdac52dd9`.
- The contract skeleton lineage is rooted at
  `d8585c707dcc6413e9fb5bb33212342918837163`.
- Draft pull request 3 targets `contract-main` from
  `codex/contract-migration`; the histories are intentionally unrelated.

## Preserved refs

- `archive/pre-contract-migration-main-20260725` preserves the former public
  `main` lineage.
- `codex/safety-contract-migration-20260725` preserves migration commit
  `c0b0b249295bdaf2299fb02ee0e8c487289cdb06`.

These refs must not be force-moved or deleted during migration.

## Safe sequence

1. Resolve the immutable skeleton contradiction and all product/evidence gaps
   on a reviewed feature branch.
2. Require green CI and a green release gate on the exact replacement commit.
3. Review the full history and file delta; keep pull request 3 draft until then.
4. Create a replacement PR into `contract-main` or supersede PR 3 with a clear
   explanation.
5. A repository owner updates the default branch to the reviewed contract
   lineage without force-pushing either lineage.
6. Update branch protection, required checks, contribution links, issue forms,
   and any external links to the selected canonical branch.
7. Fresh-clone the public URL into an empty directory and run install, tests,
   public CLI flows, and the release gate without local-only refs.
8. Close obsolete migration PRs only after linking the accepted replacement and
   archival refs.

Changing the GitHub default branch and protected settings is a human-owner
action. It remains a manual release blocker; it is not assumed complete by a
local test.
