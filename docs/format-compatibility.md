# Format compatibility and deprecation

## Capsule

Capsules declare `schema_version: "1"` and archive
`format_version: 1`. Readers reject unknown versions and unknown required
members. Version 0.x may add optional metadata fields, but may not silently
change the meaning of an existing field.

A breaking capsule change requires a new schema and archive format version,
golden read/write fixtures, an architecture decision, and a documented
migration path. RunSieve never rewrites a source capsule in place.

## Reports

Recorded-value materialization and reduction sidecars declare their mode or
format explicitly. Unknown format versions fail closed. Construction-only
properties are prose or enumerated mode properties, not measured counters.

## CLI

Before 0.2, `minimize` is a warning alias for `reduce`, and `replay` is a
warning alias for `materialize`. Scripts should migrate immediately. Removing
an alias requires a changelog entry and one tagged release containing the
warning unless a security issue requires faster removal.

Application replay is not a compatibility promise. The rejected experimental
`application_replay` field has no supported wire contract.
