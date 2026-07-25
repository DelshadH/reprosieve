# RunSieve

**Reduce a recorded failed AI-agent trajectory while preserving a declared predicate result.**

RunSieve is the public working name for the TraceCase concept. The name changed because an existing AI-agent project already uses “Tracecase” for record/replay CI. Do not restore that name without a fresh collision check.

## Target CLI

```bash
runsieve capture --output failed.runsieve -- python app.py
runsieve reduce failed.runsieve --predicate "python verify_failure.py"
runsieve materialize minimal.runsieve --output recorded-values.json
runsieve reproduce-predicate minimal.runsieve --predicate "python verify_failure.py"
runsieve export minimal.runsieve --format repro-dir --output repro/
```

Predicate protocol:

- `0`: target failure reproduced; candidate is retainable.
- `1`: target failure absent; reject reduction.
- `2`: invalid candidate or harness failure; reject reduction and preserve diagnostics.
- timeout/signal: invalid candidate.

The first adapter is the OpenAI Agents SDK. Recorded-output materialization deterministically emits retained model and tool values without executing application code. Offline predicate reproduction executes only the declared predicate in fresh constrained trials. Neither operation is application replay. K-of-N in 0.1 repeats only the predicate.

## Start Codex

Open this directory as its own repository and give Codex `CODEX_START.txt`. Its first command is:

```bash
python -m scripts.bootstrap
```

Bootstrap initializes local Git when needed, commits the immutable 72-hour execution clock into the root contract anchor, validates the contract and reference kernel, and prints the only task Codex may begin. `python -m scripts.verify` proves scaffold health; `python -m scripts.release_gate` is deliberately red until the product proofs exist.
