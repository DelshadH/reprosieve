# ReproSieve 0.1.0a4 launch

## Release notes

ReproSieve 0.1.0a4 makes the experimental alpha immediately testable without an
agent application. The new core-only `reprosieve demo` command reduces the
package-owned synthetic 247-event fixture, independently verifies 1-minimality,
materializes retained recorded values, exports an offline predicate
reproduction, and executes it. It requires no OpenAI extra, API key, external
input, or network request.

The command accepts no external capsule or predicate, so the demo itself does
not require `--trust-embedded-predicate`. Commands that consume or export
user-controlled capsules still require explicit trust because embedded
predicates are arbitrary Python.

This release changes launch usability and documentation only. It does not
change reducer behavior, capsule schemas, the predicate protocol, security
boundaries, capture or application-replay adapters, the minimality algorithm,
or public format semantics.

## Recommended launch post

ReproSieve 0.1.0a4 is live.

ReproSieve turns one failed agent trace into a smaller, redacted, deterministic
capsule that preserves the failure condition expressed by your predicate. It
then independently checks that the result is 1-minimal under its declared
reduction units.

Try the complete synthetic demonstration:

```text
pip install reprosieve==0.1.0a4
reprosieve demo
```

The demo starts with a synthetic 247-event agent trajectory, reduces it,
verifies 1-minimality, materializes the retained model and tool outputs, and
exports a standalone offline predicate reproduction. No API key or agent
application is required.

An important limitation: ReproSieve preserves what your predicate recognizes.
A weak or overly broad predicate can preserve the wrong failure.

This is an experimental alpha. Embedded predicates are arbitrary Python, the
execution controls are defense in depth rather than an OS sandbox, and
application replay is not part of the 0.1 CLI promise.

Please share synthetic or disposable examples—or describe an unsupported
failure shape. Do not send real traces, credentials, private source, personal
data, or confidential capsules.

Built end-to-end with OpenAI Codex. The source, tests, reproducible release
evidence, security boundaries, and known limitations are public.
