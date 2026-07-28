# Canonical-history migration record

The non-destructive contract-v2 migration was executed on 2026-07-26. This
record documents the result; it grants no release-tag, GitHub-release, or
registry-publication authority.

## Result

PRs 4 through 12 were retargeted and merged in dependency order with merge
commits. Their exact heads remain reachable ancestors of canonical commit
`ffabcab47d3c9fe05d3bbdc1ff8daca9a9485945`.

The former default lineage at
`a5576618444b470f6d552e163ed6ee91c5014eb3` is preserved under both
`legacy-main-pre-contract-v2-20260725` and
`archive/pre-contract-migration-main-20260725`. Contract-v1 remains reachable
through `contract-main` and draft PR 3's unchanged head. The migration safety
point is also preserved.

GitHub could not rename `contract-v2-main` directly because the old `main`
redirect reserved that name. The canonical commit was therefore exposed as a
new `main` ref through the Git data API after the old lineage was renamed and
archived. No history was force-pushed or rewritten. `contract-v2-main` remains
as an additional recovery alias at the same commit.

## Controls

The public default is `main`. It requires the Python 3.11-3.13, security,
Linux/macOS portable-reproduction, RS-G10, RS-G13, and application-replay
checks with strict up-to-date branches. Pull requests require conversation
resolution but zero human approvals. Force pushes and deletion are disabled;
linear history is not required because the preserved migration uses merge
commits.

The exact `v0.1.0a1`, `v0.1.0a2`, and `v0.1.0a3` tags are protected against
deletion and non-fast-forward updates. The `pypi` environment has no manual reviewer.
Publication is instead bound to the exact tag, canonical commit, final-evidence
receipt, immutable artifacts, and job-scoped OIDC permissions.

## Evidence and recovery

Canonical push CI run `30217885613` passed at
`ffabcab47d3c9fe05d3bbdc1ff8daca9a9485945`. A default-branch clone from the
public repository was checked independently. The machine-readable topology and
cutover state are in `docs/canonical-migration-state.json`.

Recovery is non-destructive: select
`legacy-main-pre-contract-v2-20260725` as the default if the replacement
lineage fails, preserve the failed canonical head for diagnosis, and follow
`docs/recovery.md`. Do not force-move either lineage.

PR 3 is superseded audit history and must never be merged. Publication remains
subject only to the final owner decision and available registry
authentication.
