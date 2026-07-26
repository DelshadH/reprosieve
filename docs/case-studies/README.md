# Case-study publication rules

The 247-event `killer_capsule()` is a synthetic mechanical fixture, not a real
case study. No real case is currently published.

A real case may be added only when its owner permits publication and a
maintainer confirms that the capsule contains no credentials, private source,
personal data, or contractually restricted material. Follow
[`TEMPLATE.md`](TEMPLATE.md), use the public
[`case-study-v1` schema](../../schemas/case-study-v1.schema.json), and keep
every required artifact in one directory.

Required contents:

- original redacted capsule and reduced capsule;
- executable predicate;
- reduction report and independent minimality report;
- exported reproduction;
- exact framework, Python, and dependency versions;
- permission and disclosure record;
- human explanation of retained and removed behavior;
- SHA-256 inventory for every published file.

Synthetic examples must live under `synthetic/` and say `synthetic` in both the
page title and capsule metadata.

Run `python -m scripts.verify_case_study CASE_DIRECTORY` before review. The
verifier checks canonical structure, bounded regular files, required roles,
safe paths, and hashes. It deliberately does not execute the predicate or
application and cannot authenticate the truth, authority, or scope of a
permission statement. Those remain separate human review steps.

[`registry.json`](registry.json) is the machine-readable publication ledger.
It currently contains no cases and records all three categories as external
blockers.
