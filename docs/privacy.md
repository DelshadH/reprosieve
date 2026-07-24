# Privacy and secret contract

## Before-disk invariant

No unredacted capture payload may be written to a file, logger, exception string, temporary archive, telemetry system, or crash dump by RunSieve. Default capture replaces the Agents SDK default tracing exporter; RunSieve must not silently duplicate sensitive traces to any provider backend. Transform SDK events into bounded in-memory primitives, redact, scan for canaries, then persist.

## Default redaction

- key names matching token, secret, password, authorization, cookie, api-key, private-key, or session variants;
- bearer/basic authorization material;
- common provider-key shapes;
- PEM private-key blocks;
- user-supplied exact canaries and regexes.

Replacement values are typed markers with stable salted fingerprints for equality within one capsule, not recoverable originals. Salt is capsule-local and must not enable cross-capsule tracking.

## User responsibility boundary

Arbitrary personal data cannot be inferred safely. The CLI must support key/path allowlists, deny paths, and an interactive-free dry-run redaction report. Documentation must warn users to inspect a capsule before attaching it publicly.

## Proof

Tests inject canaries into every field class, nested tool data, exceptions, logs, filenames, and malformed payloads. The gate byte-scans all produced files and process output for originals.
