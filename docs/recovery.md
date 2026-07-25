# Maintainer, registry, and release recovery

## Repository ownership

At least two maintainers should hold organization-owner recovery access before
maturity level 1.0. Each should use phishing-resistant MFA and store recovery
codes offline. Branch protection, trusted publishers, environments, and tag
rules should be reviewed quarterly and after every maintainer change.

If the sole owner loses access, no contributor should recreate releases under a
lookalike namespace. Preserve local clones and artifact hashes, use GitHub's
documented account-recovery process, and announce any canonical-location change
through previously verified project channels.

## Package registry

Prefer an OIDC trusted publisher bound to the exact repository, protected
environment, workflow filename, and tag policy. Keep a second hardware-backed
registry owner for recovery. A recovery event must rotate tokens, review owner
and publisher lists, and compare registry files with CI provenance.

## Compromised release

Freeze publishing and preserve logs. Revoke affected credentials and trusted
publishers. Yank unsafe versions without deleting historical evidence. Publish
an advisory containing affected versions and hashes, then issue a higher
version from a newly reviewed commit and clean protected workflow.

## Verification records

Store release tag, commit SHA, workflow run, wheel/sdist hashes, attestations,
registry hashes, and reviewer identity outside the package artifact. Never put
credentials, private recovery codes, or customer capsules in project evidence.
