# Release procedure

No release may be published from a dirty tree, draft pull request, red CI run,
or failing release gate.

## Candidate

1. Select an independently AI-reviewed commit on canonical `main`.
2. Run the documented local checks and inspect every security finding.
3. Confirm attested Python 3.11–3.13 package proofs and Linux/macOS
   reproduction proofs bind to the same exact commit.
4. Run `python -m scripts.final_release_gate` from a fresh clone and require
   the attestation-bound exact-head final-evidence workflow to pass. The
   immutable contract-v2 `scripts.release_gate` remains historical evidence;
   it is not rewritten to bless descendant implementation changes.
5. After the owner answers `PUBLISH? YES`, create the annotated tag
   `v0.1.0a3` on the exact canonical `main` head. Never move an existing tag.
   The unpublished `v0.1.0a1` and `v0.1.0a2` tags are retained as immutable
   records of release-workflow failures that occurred before any registry
   upload.
6. Let the release workflow export the tagged commit twice, set
   `SOURCE_DATE_EPOCH` to that commit's timestamp, require byte-identical wheel
   and sdist pairs, generate `SHA256SUMS` and an SPDX SBOM, attest the primary
   artifacts, and upload the complete proof bundle.
7. The separate `pypi` job downloads the attested bundle, verifies hashes and
   attestations, selects only the primary wheel and sdist, and publishes with a
   job-scoped OIDC trusted publisher. It does not checkout or rebuild source.
8. Create the GitHub prerelease only after the registry upload succeeds.

Independent AI technical review and exact-head CI are the alpha technical
review gate. They must be recorded honestly and are not described as human
approval. The owner's final publication decision is the only remaining manual
release authorization.

The sdist is an explicit allowlist of package source, schemas, license, readme,
security policy, changelog, and build metadata. Contract state, work logs, and
`.evidence` are intentionally absent from public distributions.

Registry authentication must use a project-scoped OIDC trusted publisher. A
long-lived token must never be stored in the repository or local evidence.

## Rollback

Do not overwrite tags or replace artifacts. If a candidate is wrong, mark it
withdrawn, retain its hashes and diagnosis, and issue a new version. If a
published package is unsafe, yank it where the registry supports yanking,
publish a security advisory, and release a higher patched version.

For suspected compromise, stop publication, revoke registry and GitHub
credentials, disable affected trusted publishers, preserve audit logs, compare
the tag and provenance to the reviewed commit, rotate signing identities, and
resume only through a new candidate. See `docs/recovery.md`.
