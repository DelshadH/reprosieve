# RunSieve

**Turn a large failed agent run into a small, redacted, offline reproduction.**

RunSieve captures one supported OpenAI Agents SDK trace, removes secrets before
persistence, replaces model and tool calls with recorded outputs, and reduces the
trace against an executable failure predicate. The result is a deterministic,
hash-addressed capsule with an independent 1-minimality proof.

> **Status:** honest pre-0.1 seed. The end-to-end path works and has synthetic
> security fixtures, but it has not been proven safe for real credentials,
> private source, or personal data. Use synthetic or disposable inputs.

## Supported path

- Python 3.11, 3.12, and 3.13.
- `openai-agents>=0.18.3,<0.19`; CI tests 0.18.3.
- One completed SDK trace captured through the public `TracingProcessor` API.
- Embedded Python predicates. RunSieve invokes them with a direct argument vector,
  a clean temporary directory, provider keys removed, bounded time/output/process
  resources, and Python audit hooks that deny outbound network, child processes,
  native loading, and host-file access.
- Deterministic recorded-output materialization. When a capsule declares an
  embedded `runsieve-recorded-v1` application adapter, predicate evaluation and
  exported reproduction run that adapter against recorded model/tool interfaces
  before checking the failure. Neither path imports the Agents SDK, calls a
  provider, or executes an original tool.

## Support matrix

| Surface | Supported |
|---|---|
| Python | 3.11, 3.12, 3.13 |
| Capture SDK | `openai-agents>=0.18.3,<0.19` |
| Standalone reproduction | Linux and macOS |
| Input safety claim | Synthetic or disposable data only |

Install the core:

```bash
python -m pip install runsieve
```

Install capture support:

```bash
python -m pip install "runsieve[openai]"
```

## Workflow

The predicate script must be included in the capsule and `--predicate` must be
the final option because everything after it is an argument vector.

```bash
runsieve capture \
  --output failed.runsieve \
  --workspace-root . \
  --include verify_failure.py \
  -- python app.py

runsieve minimize failed.runsieve \
  --output-dir reduced \
  --predicate python verify_failure.py

runsieve replay reduced/<sha256>.runsieve \
  --output replay.json

runsieve verify-minimal reduced/<sha256>.runsieve \
  --predicate python verify_failure.py

runsieve export reduced/<sha256>.runsieve \
  --output issue-repro

cd issue-repro
python reproduce.py
```

The `replay` command writes recorded outputs as JSON; by itself it does not
execute application code. Application replay is explicit and adapter-backed
during predicate evaluation and `reproduce.py`.

Predicate exit codes are strict:

- `0`: target failure reproduced.
- `1`: target failure absent.
- `2`: candidate or harness invalid.
- timeout, signal, cancellation, output overflow, unexpected exit, or missing
  predicate file: invalid.

Invalid is never treated as absent and is never accepted as a reduction.

## Reproducible proof

The repository includes a real 247-event fixture. This command builds it,
reduces it to at most 10 events, verifies 1-minimality independently, exports a
standalone reproduction, and runs it without an API key:

```bash
python scripts/killer_demo.py
```

The release gate requires this command to finish within 20 seconds. “1-minimal”
means deleting any remaining declared unit makes the failure absent or the
candidate structurally invalid. It does not mean globally smallest.

Two additional copy-paste checks:

```bash
python -m scripts.verify
python -m scripts.release_gate
```

The first runs tests, lint, typing, and contract self-tests. The second verifies
the clean Git state and every registered evidence manifest.

## Scope and comparison

RunSieve is not a trace viewer, observability backend, VM sandbox, or general
record/replay system. Existing record/replay tools preserve executions; RunSieve
adds dependency-aware reduction, redaction before its own persistence, strict
tri-state predicates, and an independently checked 1-minimality claim for one
recorded agent trajectory. It does not diagnose root cause or replay live model
semantics.

## Privacy boundary

RunSieve redacts SDK payloads in memory before its own first write. Capture
replaces the SDK default exporter unless `--retain-sdk-exporter` is explicitly
passed. Captured target stdout and stderr are discarded because they may contain
secrets. Exact canaries, bounded regexes, allow paths, deny paths, declared
workspace files, and environment allowlists are available on `capture`.

Arbitrary personal data cannot be detected reliably. Inspect every capsule
before publishing it. See [the privacy contract](docs/privacy.md) and
[security review](docs/security-review.md).

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
python -m mypy
python -m build
python scripts/security_check.py
python scripts/killer_demo.py
```

Apache-2.0 licensed.

See [SUPPORT.md](SUPPORT.md) for supported combinations and
[CONTRIBUTING.md](CONTRIBUTING.md) before opening a change.
