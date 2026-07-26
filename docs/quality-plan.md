# Quality plan

| Gate | Required proof | Reproducible evidence |
|---|---|---|
| RS-G13 | Clean Python package bootstrap | CI produces attested Python 3.11, 3.12, and 3.13 proof bundles containing reproducible wheel/sdist builds, both-distribution clean installs, core and capture-extra CLI flows, metadata/entry-point/schema parity, `SHA256SUMS`, and deterministic SPDX SBOM output. |
| RS-G01 | Official-adapter capture | `test_public_processor_captures_real_sdk_spans_without_duplicate_export` uses real 0.18.3 public spans and proves the replaced canary processor receives zero calls. |
| RS-G02 | Before-disk redaction | `test_openai_adapter.py`, `test_capsule.py`, `test_redact.py`, and CLI capture tests byte-scan synthetic canaries. |
| RS-G03 | Deterministic capsule | `test_capsule.py` proves byte equality and rejects traversal, duplicate names, symlinks, expansion, excess size, corruption, and hash mismatch. |
| RS-G04 | Offline predicate reproduction | `test_replay.py`, predicate isolation tests, and standalone export tests prove recorded values are materialized deterministically and the declared predicate reproduces with provider keys absent and network denied. Import/probe tests establish that the materializer has no provider or original-tool execution interface. Application replay declarations fail closed. |
| RS-G05 | Meaningful reduction | `killer_capsule()` contains exactly 247 validated events and reduces to 5 events, below the limit of 10. |
| RS-G06 | 1-minimality | `verify_one_minimal()` tries every declared final unit. `scripts.minimality_oracle_proof` independently enumerates the expected final unit IDs, rejects missing/duplicate attempts, and requires exact ordered coverage with no reproducing deletion. |
| RS-G07 | Tri-state correctness | Predicate tests cover reproduces, absent, invalid, timeout, signal, output overflow, missing harness, and cancellation. |
| RS-G08 | Hierarchical dependency reduction | `test_each_hierarchy_level_accepts_a_real_reduction` requires accepted span, message, pair, JSON field/item, text, file/chunk, and environment reductions. |
| RS-G09 | Probabilistic mode | The seeded three-trial fixture proves fresh directories, full attempt bookkeeping, complete cache keys, K-of-N, and the `probabilistic` label. |
| RS-G10 | Clean issue capsule | Linux and macOS jobs run `python reproduce.py` from a fresh directory without ReproSieve, a source checkout, a provider key, or network; the final workflow verifies GitHub attestations before aggregating their proofs. |
| RS-G11 | Resource bounds | Schema, redaction, capsule, predicate, capture, cancellation, recursion, output, archive, and regex limit tests cover adversarial input. |
| RS-G12 | Release experience | A clean committed tree runs `python -m scripts.verify`, then `python scripts/killer_demo.py` performs fixture creation, minimization, verification, export, and reproduction in at most 20 seconds. |

The stable gate IDs appear in CI and release notes. A small list-only delta
debugging test is not accepted as evidence for RS-G05 or RS-G06.

## Experimental 0.5 application-replay proof

The immutable RS-G01–RS-G13 registry governs 0.1 and is unchanged. A later 0.5
review additionally requires a separate gate that independently measures:

- the application callback and SDK Runner executed;
- ordered exact model/tool interactions were fully consumed;
- changed input, instructions, schemas, arguments, ordering, and early exit
  diverged;
- provider-resolution and supplied-original-tool canaries stayed at zero;
- redacted matching fields and unsupported SDK surfaces failed closed;
- the reducer removed a real unit while replay still succeeded;
- independent final-granularity verification reported 1-minimality;
- one permissioned non-synthetic case reproduced without live provider or
  original-tool execution.

Synthetic tests validate the adapter machinery. They do not satisfy the
permissioned-case or independent-evidence requirements.

## Permissioned real-case packages

`schemas/case-study-v1.schema.json` defines the bounded public package shape,
and `python -m scripts.verify_case_study` independently checks canonical
metadata, required artifact roles, regular-file/path safety, byte sizes, and
SHA-256 identities. Application-replay cases require an entry-point artifact
and replay report in addition to the reduction artifacts.

This structural result does not authenticate a data owner's authority,
permission scope, disclosure review, or the truth of the case narrative. A
human must review those claims and independently execute the declared case
before it becomes real-case or maturity evidence.

Run the complete local gate:

```bash
python -m pytest
python -m ruff check .
python -m mypy
python -m build
python -m pip_audit --strict --requirement requirements-audit.txt
python -m bandit -q -r src -lll
python scripts/security_check.py
python scripts/killer_demo.py
```
