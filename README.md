# ReproSieve

**Turn a large failed agent run into a small, redacted, offline reproduction.**

ReproSieve captures one supported OpenAI Agents SDK trace, removes secrets before
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
- Embedded Python predicates. ReproSieve invokes them with a direct argument vector,
  a clean temporary directory, provider keys removed, bounded time/output/process
  resources, and Python audit hooks that deny outbound network, child processes,
  native loading, and host-file access. These controls are defense in depth, not
  an OS sandbox; embedded predicates are arbitrary code.
- Deterministic recorded-output materialization and offline predicate
  reproduction. These paths reconstruct retained values and execute only the
  declared predicate; they do not rerun application or orchestration code.

## Support matrix

| Surface | Supported |
|---|---|
| Python | 3.11, 3.12, 3.13 |
| Capture SDK | `openai-agents>=0.18.3,<0.19` |
| Standalone reproduction | Linux and macOS |
| Input safety claim | Synthetic or disposable data only |

Install the core:

```bash
python -m pip install reprosieve
```

Install capture support:

```bash
python -m pip install "reprosieve[openai]"
```

## Workflow

The predicate script must be included in the capsule and `--predicate` must be
the final option because everything after it is an argument vector.

```bash
reprosieve capture \
  --output failed.reprosieve \
  --workspace-root . \
  --include verify_failure.py \
  -- python app.py

reprosieve reduce failed.reprosieve \
  --output-dir reduced \
  --predicate python verify_failure.py

reprosieve materialize reduced/<sha256>.reprosieve \
  --output materialized.json

reprosieve reproduce-predicate reduced/<sha256>.reprosieve \
  --predicate python verify_failure.py

reprosieve verify-minimal reduced/<sha256>.reprosieve \
  --predicate python verify_failure.py

reprosieve export reduced/<sha256>.reprosieve \
  --output issue-repro

cd issue-repro
python reproduce.py --trust-embedded-predicate
```

Exported reproductions refuse to execute without that explicit flag. Use it only
after inspecting and accepting the embedded Python predicate as arbitrary code
running with your user account's permissions.

`materialize` writes recorded values as deterministic JSON.
`reproduce-predicate` evaluates the embedded predicate in a fresh constrained
directory and reports every trial. Neither command is application replay.

The pre-0.1 `minimize` and `replay` names remain warning aliases for `reduce`
and `materialize`. They may be removed before 0.2.

Application replay is not part of the 0.1 CLI or promise. Experimental 0.5
library work now has one OpenAI Agents SDK adapter that re-executes an explicit
application callback through injected public `Model` and `FunctionTool`
interfaces. It enforces ordered exact matching and measured canaries, but
remains synthetic-only and is not a 0.5 readiness claim. See
[the application-replay boundary](docs/application-replay.md).

Predicate exit codes are strict:

- `0`: target failure reproduced.
- `1`: target failure absent.
- `2`: candidate or harness invalid.
- timeout, signal, cancellation, output overflow, unexpected exit, or missing
  predicate file: invalid.

Invalid is never treated as absent and is never accepted as a reduction.

## Reproducible proof

The repository includes a synthetic 247-event mechanical fixture. This command builds it,
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

ReproSieve is not a trace viewer, observability backend, VM sandbox, or general
record/replay system. Existing record/replay tools preserve executions; ReproSieve
adds dependency-aware reduction, redaction before its own persistence, strict
tri-state predicates, and an independently checked 1-minimality claim for one
recorded agent trajectory. It does not diagnose root cause, rerun application
logic, or replay live model semantics.

## Privacy boundary

ReproSieve redacts SDK payloads in memory before its own first write. Capture
replaces the SDK default exporter unless `--retain-sdk-exporter` is explicitly
passed. Captured target stdout and stderr are discarded because they may contain
secrets. Exact canaries, bounded regexes, allow paths, deny paths, declared
workspace files, and environment allowlists are available on `capture`.

Arbitrary personal data cannot be detected reliably. Inspect every capsule
before publishing it. See [the privacy contract](docs/PRIVACY.md) and
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
[CONTRIBUTING.md](CONTRIBUTING.md) before opening a change. Maturity levels are
defined in [ROADMAP.md](ROADMAP.md); real-case evidence status is tracked in
[docs/case-studies](docs/case-studies/README.md).
