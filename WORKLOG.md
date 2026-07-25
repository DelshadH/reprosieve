# RunSieve work log

Append one entry for every task attempt. Do not rewrite prior entries. Evidence and Git history remain authoritative; this log records decisions, failed approaches, and deadline pivots.

## Entry template

```text
## <UTC timestamp> — <task ID> — attempt <n>
Objective: <one falsifiable sentence>
Starting commit: <full SHA>
Deadline state: <elapsed hours>/<task deadline_hour>; <within budget|kill/pivot applied>
Approach: <smallest vertical slice attempted>
Commands: <exact commands or links to evidence manifests>
Result: <passed|failed|blocked>
Observed facts: <outputs, counterexamples, measurements>
Decision: <continue|change approach|apply exact kill_or_pivot>
Ending commit: <full SHA or "uncommitted failure investigation">
Manual item: <MANUAL_REQUIRED.json ID or "none">
```

No entries yet. Bootstrap and task RS-000 begin the log.

## 2026-07-25T18:50:00Z — RS-000 — attempt 1
Objective: Port the accepted c866277 implementation without changing any contract-v2 immutable byte.
Starting commit: 8686965f35a6521400e404891a72fb5d8dc3471d
Deadline state: 0.27/4 hours; within budget
Approach: Copy only the 104 paths in docs/contract-v2-port.json, retain fresh v2 state, adapt G04/G09/G12 assertion semantics, and create a newly reviewed secret baseline.
Commands: contract-v2 allowlist port; focused red/green gate tests; `python -m scripts.verify`
Result: passed
Observed facts: The immutable bundle remains unchanged; 96 tests plus 2 subtests, Ruff, and strict mypy pass; the reviewed baseline contains exactly 21 non-secret contract/fixture findings.
Decision: commit the implementation port before generating any contract-v2 evidence.
Ending commit: pending implementation-port commit
Manual item: none

## 2026-07-25T19:16:00Z — RS-010 — attempt 1
Objective: Measure public SDK capture without private imports, duplicate export, or unstated replay.
Starting commit: a660531a0fec1479545227a248fc68448ca9646a
Deadline state: 0.65/12 hours; within budget
Approach: Run the gate-specific verifier from a clean detached worktree.
Commands: `.evidence/RS-G01/local-a660531-g01/manifest.json`
Result: passed
Observed facts: All five RS-G01 assertions were independently derived from recorded command output and committed adapter bytes.
Decision: accept the gate evidence.
Ending commit: pending evidence-registration commit
Manual item: none

## 2026-07-25T19:16:01Z — RS-020 — attempt 1
Objective: Measure redaction-before-write and deterministic hostile-input-safe capsule construction.
Starting commit: a660531a0fec1479545227a248fc68448ca9646a
Deadline state: 0.65/24 hours; within budget
Approach: Run RS-G02 and RS-G03 separately from clean detached worktrees.
Commands: `.evidence/RS-G02/local-a660531-g02/manifest.json`; `.evidence/RS-G03/local-a660531-g03/manifest.json`
Result: passed
Observed facts: Secret canaries remained absent and traversal, archive bombs, malformed references, and member-hash failures were rejected.
Decision: accept both gate manifests.
Ending commit: pending evidence-registration commit
Manual item: none

## 2026-07-25T19:16:02Z — RS-030 — attempt 1
Objective: Measure constrained predicate-only reproduction against deterministic recorded values.
Starting commit: a660531a0fec1479545227a248fc68448ca9646a
Deadline state: 0.65/36 hours; within budget
Approach: Run the seven RS-G04 measurements and provider/tool canaries.
Commands: `.evidence/RS-G04/local-a660531-g04/manifest.json`
Result: passed
Observed facts: The declared predicate reproduced the target while provider and original-tool canaries remained untouched.
Decision: accept the predicate-reproduction evidence without an application-replay claim.
Ending commit: pending evidence-registration commit
Manual item: none

## 2026-07-25T19:16:03Z — RS-040 — attempt 1
Objective: Measure tri-state behavior and independent final-granularity 1-minimality.
Starting commit: a660531a0fec1479545227a248fc68448ca9646a
Deadline state: 0.65/52 hours; within budget
Approach: Run RS-G06 and RS-G07 in distinct clean worktrees.
Commands: `.evidence/RS-G06/local-a660531-g06/manifest.json`; `.evidence/RS-G07/local-a660531-g07/manifest.json`
Result: passed
Observed facts: Every final unit removal was checked, invalid outcomes stayed distinct, and timeout/signal cases remained invalid.
Decision: accept both gate manifests.
Ending commit: pending evidence-registration commit
Manual item: none

## 2026-07-25T19:16:04Z — RS-050 — attempt 1
Objective: Measure the killer reduction and every declared hierarchical reducer class.
Starting commit: a660531a0fec1479545227a248fc68448ca9646a
Deadline state: 0.65/68 hours; within budget
Approach: Run RS-G05 and RS-G08 against committed fixtures and generated graphs.
Commands: `.evidence/RS-G05/local-a660531-g05/manifest.json`; `.evidence/RS-G08/local-a660531-g08/manifest.json`
Result: passed
Observed facts: The 247-event fixture reduced to at most 10 events with its predicate and graph integrity preserved; all seven reducer classes passed.
Decision: accept both gate manifests.
Ending commit: pending evidence-registration commit
Manual item: none

## 2026-07-25T19:16:05Z — RS-060 — attempt 1
Objective: Measure repeated predicate trials and portable one-command export on Linux and macOS.
Starting commit: a660531a0fec1479545227a248fc68448ca9646a
Deadline state: 0.65/80 hours; within budget
Approach: Generate RS-G09 locally and aggregate runner-produced RS-G10 proofs in GitHub Actions.
Commands: `.evidence/RS-G09/local-a660531-g09/manifest.json`; `.evidence/RS-G10/github-30171123965-1/manifest.json`; CI run 30171123965
Result: passed
Observed facts: Trial bookkeeping was complete; exact-commit Linux and macOS artifacts passed all five portable-reproduction assertions.
Decision: accept both gate manifests.
Ending commit: pending evidence-registration commit
Manual item: none

## 2026-07-25T19:16:06Z — RS-070 — attempt 1
Objective: Measure the declared timeout, output, event, archive, recursion, and cancellation limits.
Starting commit: a660531a0fec1479545227a248fc68448ca9646a
Deadline state: 0.65/90 hours; within budget
Approach: Run the six RS-G11 adversarial measurements from a clean worktree.
Commands: `.evidence/RS-G11/local-a660531-g11/manifest.json`
Result: passed
Observed facts: Every bounded-resource assertion was derived from its selected test output.
Decision: accept the gate evidence within the documented Python boundary.
Ending commit: pending evidence-registration commit
Manual item: none

## 2026-07-25T19:16:07Z — RS-080 — attempt 1
Objective: Measure the complete clean-room 0.1 claim after binding every CI checkout to an exact commit.
Starting commit: 9110228be9caadccd864c40ba675329e5a2b07b2
Deadline state: 0.65/96 hours; within budget
Approach: Run full contract verification and the killer demo from a clean detached worktree.
Commands: `.evidence/RS-G12/local-9110228-g12/manifest.json`
Result: passed
Observed facts: Contract-v2 self-tests, 97 tests plus 2 subtests, Ruff, strict mypy, reduction, materialization, predicate reproduction, export, and 1-minimality all passed.
Decision: accept the clean-room release-candidate evidence.
Ending commit: pending evidence-registration commit
Manual item: none

## 2026-07-25T19:16:08Z — RS-000 — attempt 2
Objective: Measure clean builds and installed-package CLI behavior across Python 3.11 through 3.13.
Starting commit: 9110228be9caadccd864c40ba675329e5a2b07b2
Deadline state: 0.65/4 hours; within budget
Approach: Use exact-head CI checkouts, runner-produced wheels and sdists, clean smoke environments, and the RS-G13 aggregator.
Commands: `.evidence/RS-G13/github-30171123965-1/manifest.json`; CI run 30171123965
Result: passed
Observed facts: All three Python jobs, security, both platform jobs, and both CI evidence aggregators completed successfully at the same commit.
Decision: register the final evidence set and run the independent release gate.
Ending commit: pending evidence-registration commit
Manual item: none

## 2026-07-25T19:48:17Z — RS-000 — attempt 3
Objective: Produce a `0.1.0a1` wheel and public sdist twice from one clean commit with byte-identical results.
Starting commit: 04c3d6b5dc1d9dd1c1911f80e8e23c43ebe928b2
Deadline state: 1.18/4 hours; within budget
Approach: Use an explicit Hatch sdist allowlist, commit-derived `SOURCE_DATE_EPOCH`, two clean exports, installed-wheel smoke, and CI aggregation on Python 3.11-3.13.
Commands: `.evidence/RS-G13/github-30172192165-1/manifest.json`; CI run 30172192165
Result: passed
Observed facts: Every Python job produced byte-identical rebuilds; the sdist shrank from 704287 bytes to 42872 bytes and contains no evidence or control-plane state.
Decision: replace the superseded package evidence and retain the full reproducibility proof bundle.
Ending commit: pending release-evidence registration commit
Manual item: none

## 2026-07-25T19:48:18Z — RS-080 — attempt 2
Objective: Re-run the complete clean-room 0.1 proof after package metadata and release-verifier changes.
Starting commit: 04c3d6b5dc1d9dd1c1911f80e8e23c43ebe928b2
Deadline state: 1.18/96 hours; within budget
Approach: Run full verification and the killer demo from a fresh detached worktree.
Commands: `.evidence/RS-G12/local-04c3d6b-g12/manifest.json`
Result: passed
Observed facts: The all-passed contract self-test, 99 tests plus 2 subtests, Ruff, strict mypy, reduction, materialization, predicate reproduction, export, and 1-minimality passed.
Decision: replace the superseded clean-room evidence.
Ending commit: pending release-evidence registration commit
Manual item: none

## 2026-07-25T20:10:12Z — RS-080 — attempt 3
Objective: Re-prove the complete 0.1 release after making Git-tracked evidence a release-gate invariant.
Starting commit: 91f5bb5e6d7d0719795927dbf16c83f8cfde02e7
Deadline state: 1.55/96 hours; within budget
Approach: Run the full verifier and killer demo from the clean implementation commit after committing the missing G10 capsule artifacts.
Commands: `.evidence/RS-G12/release-tracking-fix-91f5bb5/manifest.json`
Result: passed
Observed facts: Contract self-tests, 100 tests plus 2 subtests, Ruff, strict mypy, reduction, materialization, predicate reproduction, export, and 1-minimality passed.
Decision: replace superseded G12 evidence; require every release-evidence blob to exist in Git and in HEAD.
Ending commit: pending release-evidence registration commit
Manual item: none
