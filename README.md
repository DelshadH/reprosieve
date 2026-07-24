# RunSieve

**Turn a large failed agent run into a small, redacted, offline reproduction.**

RunSieve captures a supported run, replaces model and tool calls with recorded
outputs, and removes events that are not needed to reproduce a user-defined
failure. The result is a deterministic capsule that can be attached to an issue
or used as a regression fixture without calling the original provider.

> **Status:** pre-0.1 development. The schema, redaction helper, and generic
> delta-debugging kernel are present. Capture, capsule I/O, hermetic replay, and
> the complete CLI are still under construction. Use only synthetic data.

## Intended workflow

```bash
runsieve capture --output failed.runsieve -- python app.py
runsieve minimize failed.runsieve --predicate "python verify_failure.py"
runsieve replay minimal.runsieve --offline
runsieve export minimal.runsieve --format repro-dir --output repro/
```

The predicate protocol is intentionally small:

- `0`: the target failure reproduced; the candidate may be retained.
- `1`: the target failure was absent; reject the reduction.
- `2`: the candidate or harness was invalid; reject it and keep diagnostics.
- timeout or signal: invalid.

The default replay mode never calls a model provider or an original external
tool. “Minimal” means 1-minimal under the documented reduction units: removing
any one remaining unit either loses the failure or makes the capsule invalid. It
does not mean globally smallest.

## First supported adapter

The initial capture adapter targets the public tracing processor interface in the
OpenAI Agents SDK. RunSieve converts SDK objects into its own versioned format and
redacts sensitive values before persistence.

See [docs/product.md](docs/product.md), [docs/architecture.md](docs/architecture.md),
and [docs/privacy.md](docs/privacy.md) for the exact boundaries.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
python -m mypy
```

Contributions should begin with a failing reduction, replay, privacy, or malformed
input fixture. Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

Apache-2.0 licensed.
