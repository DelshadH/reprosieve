# Canonical-history migration plan

This is a preparation runbook, not authorization to merge, rename a public
branch, change the default branch, publish a package, or close an audit pull
request. Repository-owner actions remain pending.

## Verified topology

| Ref or PR | Exact commit | State and role |
|---|---|---|
| `main` | `a5576618444b470f6d552e163ed6ee91c5014eb3` | Current public default; unrelated former implementation |
| `archive/pre-contract-migration-main-20260725` | `a5576618444b470f6d552e163ed6ee91c5014eb3` | Preserved former-main archive |
| `contract-main` | `d8585c707dcc6413e9fb5bb33212342918837163` | Immutable contract-v1 root |
| PR 3: `codex/contract-migration` | `c866277d061130d8942ed37fe855bd708110b1f8` | Unchanged draft contract-v1 audit history |
| `contract-v2-main` | `8686965f35a6521400e404891a72fb5d8dc3471d` | Unrelated corrected one-root contract-v2 lineage |
| PR 4: `codex/contract-v2-migration` | `1aaf298ee5927fc644ecad07df436fc9a6f4399d` | Draft accepted implementation and 0.1 evidence |
| PR 5: `codex/contract-v2-release-engineering` | `1324d3c1cf1b452100a42c263e1cf88f1cff4b69` | Draft reproducible 0.1 alpha candidate |
| PR 6: `codex/canonical-migration-prep` | `fb92df6bd287e4e5e9023abf29f8b5b3d88eb5db` | Draft non-destructive migration runbook |
| `codex/safety-contract-migration-20260725` | `c0b0b249295bdaf2299fb02ee0e8c487289cdb06` | Preserved migration safety point |

PR 4 CI run `30171448917` and PR 5 CI run `30173363931` passed every
Python 3.11–3.13, security, Linux, macOS, RS-G10, and RS-G13 job. A new
public clone of PR 5's exact head passed the full verifier and release gate.
PR 6 CI run `30173726922` passed the same matrix. None has an independent
review or approval yet. The current `main` branch has no readable
branch-protection rule.

The machine-readable snapshot in `docs/canonical-migration-state.json` records
the canonical cutover preconditions observed before PR 6. Later experimental
work is deliberately not a prerequisite for the 0.1 cutover.

## Later stacked work

The following draft PRs are stacked after PR 6 and must not be silently folded
into the 0.1 migration decision:

| PR | Exact head | State and claim boundary |
|---|---|---|
| PR 7: `codex/openai-agents-application-replay` | `ab0d27cfa190afad7dd8e77410b0dec2f2d9ef60` | Green independent synthetic application-replay evidence; not 0.5-ready |
| PR 8: `codex/permissioned-case-study-infrastructure` | `5aadfe1240daa85893e6f7c2f9101a03befd9884` | Green case-package infrastructure; zero real cases |
| PR 9: `codex/one-zero-readiness` | `c6b5982327346f98537494846680e18063e0b933` | Green external-validation and maturity governance |
| PR 10: `codex/case-study-junction-hardening` | `9f6039dadd3e01d8fb580f253e458ebbebf96a4a` | Green junction/reparse-point hardening |
| PR 11: `codex/completion-audit` | current draft head | Full objective and evidence-principle audit; exact-head CI required |

After the canonical default switch, retarget and independently review these
PRs in numerical order. Preserve merge commits so measured ancestor identities
remain reachable. PR 7 cannot support a 0.5 readiness decision without
permissioned real-case evidence; PRs 8 through 10 do not create that evidence.
PR 11 records that distinction but does not satisfy any external blocker.

## Invariants

- Never force-push, rebase, or squash a migration branch.
- Preserve every ref and commit listed above until the replacement has been
  independently reviewed, selected as default, cloned, and recovery-tested.
- Use GitHub's **Create a merge commit** method. Squash creates one replacement
  commit and GitHub rebase creates new commit SHAs; either would make recorded
  evidence commits non-ancestral and the release gate would reject the result.
- Do not enable a linear-history rule on the replacement branch because this
  migration requires merge commits.
- Do not mark PR 3 merged. It is the immutable contract-v1 audit trail.
- Do not claim post-migration fresh-clone evidence before the public default
  branch has actually changed.

## Owner sequence

1. Independently review PR 4's contract-v1/v2 diff, allowlisted port, evidence,
   and complete commit history. Mark it ready only after approval.
2. Protect `contract-v2-main`: require pull requests, at least one independent
   approval, conversation resolution, and these exact successful CI checks:
   `test (3.11)`, `test (3.12)`, `test (3.13)`, `security`,
   `portable-reproduction (ubuntu-latest, linux)`,
   `portable-reproduction (macos-latest, macos)`, `rs-g10-evidence`, and
   `rs-g13-evidence`. Keep force pushes and deletion disabled. Do not require
   linear history.
3. Merge PR 4 into `contract-v2-main` with **Create a merge commit**. Confirm
   `1aaf298ee5927fc644ecad07df436fc9a6f4399d` remains an ancestor.
4. Retarget PR 5 from `codex/contract-v2-migration` to
   `contract-v2-main`. Re-run every check at exact head
   `1324d3c1cf1b452100a42c263e1cf88f1cff4b69`, review it independently,
   and merge it with **Create a merge commit**.
5. Retarget PR 6 to `contract-v2-main`, review the runbook and snapshot,
   re-run every check at exact head
   `fb92df6bd287e4e5e9023abf29f8b5b3d88eb5db`, and merge it with
   **Create a merge commit**.
6. From a new clone of `contract-v2-main`, verify the expected head, a clean
   tree, `python -m scripts.verify`, `python -m scripts.release_gate`, installed
   wheel CLI flows, and evidence ancestry. Stop if any check differs.
7. Rename the existing default `main` to
   `legacy-main-pre-contract-v2-20260725`; do not delete it. Then rename the
   reviewed `contract-v2-main` to `main` and set that branch as the default.
   GitHub branch renames preserve commit history and update ordinary GitHub
   links, protection policies, and open PR base branches, but raw URLs and
   local Git tracking require explicit updates.
8. Verify the CI workflow in the replacement tree still targets `main`.
   Update repository rules, issue forms, contribution links, release settings,
   and any external raw links that referred to the old branch.
9. Clone the public repository URL with no branch override into another empty
   directory. Repeat installation, full verification, public CLI flows, and
   the release gate. Record the exact default-head SHA and CI run.
10. Only after step 9, close PR 3 as superseded—never merged—with links to the
   archived refs, contract-v2 root, accepted PRs, and post-switch evidence.
   Keep the legacy and safety branches.
11. Retarget PRs 7 through 11 onto the new `main` in order. Review and merge
    each independently only if its own maturity boundary and exact-head CI are
    accepted. Do not present their presence as real-case or adoption evidence.

If a merge, rename, or protection edit changes a commit SHA or ancestry,
regenerate every affected proof rather than editing its recorded identity.

## Recovery

Before the switch, verify all preserved refs with `git ls-remote`. If the new
default fails after migration, change the default back to
`legacy-main-pre-contract-v2-20260725`; do not rewrite either lineage. Preserve
the failing replacement head for diagnosis. Follow `docs/recovery.md` for a
compromised artifact or account.

## Owner-only blockers

- Independent human review and approval of PRs 4, 5, and 6.
- Branch-protection/ruleset creation.
- Merge-commit selection and merges.
- Public branch renames and default-branch selection.
- Post-switch external fresh-clone validation.
- Closing PR 3 with a human-reviewed supersession notice.
- Separate review and disposition of later PRs 7 through 11.

GitHub documents that default-branch changes require admin access, branch
renames require elevated permissions for a default/protected branch, merge
commits preserve the pull-request commits, and branch protection can require
reviews and status checks:

- <https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-branches-in-your-repository/renaming-a-branch>
- <https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-branches-in-your-repository/changing-the-default-branch>
- <https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/about-merge-methods-on-github>
- <https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches>
