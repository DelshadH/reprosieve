# Independent external validation

External reports can strengthen ReproSieve evidence only when they identify
exactly what was executed. A report is not accepted merely because it contains
a hash, a passing screenshot, or the name of a configured assertion.

## Safe validation scope

Use a full commit SHA, a fresh clone or installed artifact, and synthetic or
explicitly permissioned data. Never post credentials, private source, personal
data, raw production traces, unpublished permission records, or registry
secrets in an issue.

For the 0.1 contract, record:

- repository and full commit SHA;
- clean-checkout or artifact identity and SHA-256;
- operating system, architecture, and Python version;
- exact argument-vector commands and exit codes;
- bounded stdout/stderr or their hashes;
- whether provider credentials and source-tree dependencies were absent;
- `scripts.verify`, package smoke, portable reproduction, and release-gate
  results.

For experimental application replay, separately identify:

- the application callback and SDK version actually executed;
- the adapter protocol and matching mode;
- model and tool interactions consumed;
- provider-resolution and original-tool canary counts;
- every divergence probe performed;
- whether the input was synthetic or permissioned real-case material.

Running only materialization or a predicate is not application replay.

## Submission and acceptance

Use the independent-validation issue form for non-sensitive reports. Attach
only synthetic artifacts. For a permissioned real case, follow
`docs/case-studies/README.md` and propose the reviewed package through a narrow
pull request; do not expose private authorization material in a public issue.

A maintainer accepts external evidence only after:

1. checking the commit and artifact ancestry;
2. reviewing commands, environment, and raw bounded results;
3. reproducing the relevant verifier independently;
4. confirming that the claim matches the operation actually executed;
5. recording limitations, reviewer identity, and the accepted evidence hash.

Self-reported use is useful feedback but does not automatically satisfy
sustained-use, permission, security-review, or maturity gates. Multiple active
maintainers and sustained independent use remain external 1.0 requirements.
