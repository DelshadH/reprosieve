# Release procedure

No release may be published from a dirty tree, draft pull request, red CI run,
or failing release gate.

## Candidate

1. Select a reviewed commit on the canonical branch.
2. Run the documented local checks and inspect every security finding.
3. Confirm Python 3.11–3.13 package proofs and Linux/macOS reproduction proofs
   bind to the same commit.
4. Run `python -m scripts.release_gate` from a fresh clone.
5. Create an annotated release-candidate tag without moving an existing tag.
6. Let the protected release workflow export the tagged commit twice, set
   `SOURCE_DATE_EPOCH` to that commit's timestamp, require byte-identical wheel
   and sdist pairs, attest the canonical pair, and upload the complete proof
   bundle.
7. Download the bundle into an empty directory, verify attestations and hashes,
   install each distribution without the source tree, and run all public CLI
   flows.
8. Publish only after a human owner compares the reviewed commit, tag, workflow
   run, artifact hashes, and changelog.

The sdist is an explicit allowlist of package source, schemas, license, readme,
security policy, changelog, and build metadata. Contract state, work logs, and
`.evidence` are intentionally absent from public distributions.

Registry credentials must use a project-scoped trusted publisher or a
hardware-backed account with 2FA. They must never be stored in the repository
or local evidence.

## Rollback

Do not overwrite tags or replace artifacts. If a candidate is wrong, mark it
withdrawn, retain its hashes and diagnosis, and issue a new version. If a
published package is unsafe, yank it where the registry supports yanking,
publish a security advisory, and release a higher patched version.

For suspected compromise, stop publication, revoke registry and GitHub
credentials, disable affected trusted publishers, preserve audit logs, compare
the tag and provenance to the reviewed commit, rotate signing identities, and
resume only through a new candidate. See `docs/recovery.md`.
