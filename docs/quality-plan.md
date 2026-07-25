# Quality plan

| Gate | Required proof | Reproducible evidence |
|---|---|---|
| RS-G13 | Clean Python package bootstrap | CI produces gate-specific Python 3.11, 3.12, and 3.13 proof bundles containing clean-checkout build outputs, wheel/sdist hashes, clean-install outputs, and CLI smoke output. |
| RS-G01 | Official-adapter capture | `test_public_processor_captures_real_sdk_spans_without_duplicate_export` uses real 0.18.3 public spans and proves the replaced canary processor receives zero calls. |
| RS-G02 | Before-disk redaction | `test_openai_adapter.py`, `test_capsule.py`, `test_redact.py`, and CLI capture tests byte-scan synthetic canaries. |
| RS-G03 | Deterministic capsule | `test_capsule.py` proves byte equality and rejects traversal, duplicate names, symlinks, expansion, excess size, corruption, and hash mismatch. |
| RS-G04 | Offline hermetic replay | `test_replay.py`, predicate isolation tests, and standalone export tests prove a declared application adapter executes against recorded interfaces with zero provider/original-tool calls, keys absent, and network denied. The standalone `replay` command is tested only as recorded-output materialization. |
| RS-G05 | Meaningful reduction | `killer_capsule()` contains exactly 247 validated events and reduces to 5 events, below the limit of 10. |
| RS-G06 | 1-minimality | `verify_one_minimal()` independently tries every declared final unit; `test_hierarchy.py` requires no reproducing deletion. |
| RS-G07 | Tri-state correctness | Predicate tests cover reproduces, absent, invalid, timeout, signal, output overflow, missing harness, and cancellation. |
| RS-G08 | Hierarchical dependency reduction | `test_each_hierarchy_level_accepts_a_real_reduction` requires accepted span, message, pair, JSON field/item, text, file/chunk, and environment reductions. |
| RS-G09 | Probabilistic mode | The seeded three-trial fixture proves fresh directories, full attempt bookkeeping, complete cache keys, K-of-N, and the `probabilistic` label. |
| RS-G10 | Clean issue capsule | CLI end-to-end tests run `python reproduce.py` from a fresh directory without RunSieve, a source checkout, a provider key, or network. |
| RS-G11 | Resource bounds | Schema, redaction, capsule, predicate, capture, cancellation, recursion, output, archive, and regex limit tests cover adversarial input. |
| RS-G12 | Release experience | A clean committed tree runs `python -m scripts.verify`, then `python scripts/killer_demo.py` performs fixture creation, minimization, verification, export, and reproduction in at most 20 seconds. |

The stable gate IDs appear in CI and release notes. A small list-only delta
debugging test is not accepted as evidence for RS-G05 or RS-G06.

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
