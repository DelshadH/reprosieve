# RunSieve

**Turn a large failed AI-agent run into the smallest hermetic reproduction that still fails.**

RunSieve is the public working name for the TraceCase concept. The name changed because an existing AI-agent project already uses “Tracecase” for record/replay CI. Do not restore that name without a fresh collision check.

## Target CLI

```bash
runsieve capture --output failed.runsieve -- python app.py
runsieve minimize failed.runsieve --predicate "python verify_failure.py"
runsieve replay minimal.runsieve --offline
runsieve export minimal.runsieve --format repro-dir --output repro/
```

Predicate protocol:

- `0`: target failure reproduced; candidate is retainable.
- `1`: target failure absent; reject reduction.
- `2`: invalid candidate or harness failure; reject reduction and preserve diagnostics.
- timeout/signal: invalid candidate.

The first adapter is the OpenAI Agents SDK. Offline replay uses captured model and tool outputs, requires no API key, and is the default minimization mode. Live probabilistic mode is later in the v0.1 graph and cannot replace offline proof.

## Start Codex

Open this directory as its own repository and give Codex `CODEX_START.txt`. Its first command is:

```bash
python -m scripts.bootstrap
```

Bootstrap initializes local Git when needed, commits the immutable 72-hour execution clock into the root contract anchor, validates the contract and reference kernel, and prints the only task Codex may begin. `python -m scripts.verify` proves scaffold health; `python -m scripts.release_gate` is deliberately red until the product proofs exist.
