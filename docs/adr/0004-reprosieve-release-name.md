# ADR 0004: ReproSieve is the public release name

## Decision

The unpublished 0.1 public product, Python distribution, import package,
executable, capsule suffix, and repository target use `ReproSieve` /
`reprosieve`.

## Reason

The final pre-publication collision check on 2026-07-26 found an active,
independently owned project using RunSieve as its product name and `runsieve`
as its Python distribution, import package, and executable. Publishing under
that exact surface would create avoidable user confusion.

The replacement check found no exact GitHub repository named `reprosieve` and
PyPI returned no project for `reprosieve` at the time of the check. This is a
point-in-time collision check, not a trademark opinion.

## Compatibility and audit lineage

The contract-v2 root and its immutable control-plane files keep the historical
project identifier `runsieve`. The two historical source paths required by
that immutable contract remain in the repository but are excluded from wheel
and sdist artifacts.

Uppercase `RUNSIEVE_*` environment names remain a stable internal evidence and
reproduction protocol for 0.1. They are not the public executable or import
package. Renaming those values would invalidate existing evidence without
improving the user-facing collision boundary.

No RunSieve package was published, so no package migration or compatibility
alias is shipped.
