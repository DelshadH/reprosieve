# Release standard

A public v0.1 release is allowed only when all of the following are true:

- A clean checkout can install, build, test, and run the killer demo from one documented command.
- The killer demo demonstrates the product's unique claim, not merely its CLI.
- Every release claim maps to a machine-checked proof gate.
- Failure output tells both a human and a coding agent what changed and how to reproduce it.
- Inputs that may contain secrets are redacted before persistence and covered by canary tests.
- CI uses least privilege, no untrusted-code workflow receives secrets, and actions are pinned for release.
- The repository includes license, security policy, contribution guide, code of conduct, issue forms, changelog, support policy, and architecture boundaries.
- The project has a generated terminal demo under 20 seconds and three copy-paste examples.
- Package names, executable names, and repository names have been checked immediately before publishing.

“Works on the author's machine” and “the unit tests pass” are necessary but insufficient.
