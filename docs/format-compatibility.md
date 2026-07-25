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

## Permissioned case studies

Case-study packages declare integer `schema_version: 1` and conform to
`schemas/case-study-v1.schema.json`. A published package is immutable: changing
any manifest or artifact byte requires a new case revision and registry
identity, never an in-place replacement.

The structural verifier rejects unknown fields, unsafe or duplicate paths and
roles, symbolic links, unbounded files, missing roles, hash/size mismatches,
unrecorded files, and application-replay packages without an entry point and
replay report. Schema validity and hashes do not authenticate permission,
disclosure safety, or narrative truth; those remain human-reviewed evidence.

A breaking package change requires a new schema version, compatibility fixture,
architecture decision, and migration note. No real case-study package is
published yet.

## CLI

Before 0.2, `minimize` is a warning alias for `reduce`, and `replay` is a
warning alias for `materialize`. Scripts should migrate immediately. Removing
an alias requires a changelog entry and one tagged release containing the
warning unless a security issue requires faster removal.

The experimental OpenAI Agents application-replay protocol is versioned as
`openai-agents-public-v1` for fail-closed matching, but is not yet a stable
compatibility promise. The rejected 0.1 `application_replay` predicate field
still has no supported wire contract.
