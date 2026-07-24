# Privacy and secret contract

## Before-disk invariant

RunSieve does not write an unredacted capture payload to its files, archives,
logs, exceptions, telemetry, or target-output relay. The adapter converts each
completed public SDK span to bounded in-memory primitives, redacts it, and only
then allows capsule construction. Target stdout and stderr are discarded.

Capture replaces the Agents SDK default trace processors. The
`--retain-sdk-exporter` option weakens this privacy boundary intentionally and is
never enabled implicitly.

This contract covers RunSieve. It cannot prevent the captured application,
provider SDK, operating system, debugger, or crash reporter from writing its own
data.

## Default redaction

The default policy covers:

- keys containing token, secret, password, authorization, cookie, API key,
  private key, or session variants;
- bearer/basic credentials and common provider-key forms;
- PEM private-key blocks;
- user-declared exact canaries;
- a conservative bounded regex subset;
- explicit deny paths.

Deny paths win. Allow paths may suppress key-name redaction but never suppress
exact-canary or token-shape redaction. Full-value replacements are typed markers
with a salted fingerprint. Partial-string replacements use the same
capsule-local fingerprint. The random salt is not persisted, so equal values are
linkable only inside one capture.

Grouping, alternation, counted repetition, backreferences, and multiple
unbounded wildcards are rejected in user regexes because Python's standard
regular-expression engine has no evaluation timeout.

## Declared data only

Capture reads only explicitly named UTF-8 workspace files and environment
entries. It rejects traversal, symlink/junction components, non-files, invalid
UTF-8, duplicate sanitized paths, excess files, and excess bytes. A secret in a
declared filename or environment name is replaced with a safe salted name.

Arbitrary personal information cannot be inferred safely. A successful
redaction report is evidence that configured patterns were removed, not proof
that a capsule is anonymous. Byte-scan and inspect a capsule before publishing
it.

## Tests

Privacy tests inject synthetic canaries into trace metadata, model input, tool
arguments/results, workspace content, environment values, filenames, malformed
spans, predicate output, and exported files. Produced capsule bytes and captured
CLI streams are scanned for the original canaries.
