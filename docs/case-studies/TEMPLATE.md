# Permissioned real-case package template

Status: template only; not case evidence

Do not create a case entry until a data owner has authorized publication and a
maintainer can review the exact public bytes. Store only an owner-approved
public identifier in repository metadata; do not commit private contact
details or unpublished authorization material.

Each case directory contains canonical `case-study.json` conforming to
`schemas/case-study-v1.schema.json`. Its category is exactly one of:

- `unexpected-tool-result`;
- `serialization-structured-output`;
- `application-model-trajectory`.

The manifest distinguishes what application or predicate code was re-executed
from what recorded values were only materialized. It records exact framework,
Python, operating-system, architecture, command, expected exit code,
limitations, retained behavior, and removed behavior.

Every package requires these hash-bound artifact roles:

- `original-capsule`;
- `reduced-capsule`;
- `predicate`;
- `reduction-report`;
- `minimality-report`;
- `export`;
- `dependency-inventory`;
- `permission-record`.

An `application-replay` case also requires `application-entrypoint` and
`application-replay-report`. The entry point is reviewed application source,
not a capsule-supplied command that RunSieve silently executes.

The permission record must state the publication scope for the exact package
bytes. A disclosure reviewer separately checks credentials, private source,
personal data, contractual restrictions, and redaction limitations. Passing
the structural verifier proves neither permission authenticity nor disclosure
safety.

Before proposing publication:

```bash
python -m scripts.verify_case_study docs/case-studies/real/<case-id>
```

Then run the case's declared command from a fresh constrained directory,
retain its bounded output as independent evidence, and update `registry.json`
only after human permission and disclosure review.
