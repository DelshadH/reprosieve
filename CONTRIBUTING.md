# Contributing

RunSieve handles data that may contain credentials, source code, and personal
information. Read `docs/privacy.md` and `docs/architecture.md` before changing
capture, storage, replay, or export behavior.

Keep pull requests narrow and begin behavior changes with a failing fixture.
Reducer changes need an independent 1-minimality check and differential oracle
coverage. Materialization and predicate changes must preserve the no-provider,
no-original-tool execution boundary. Do not describe JSON extraction as
application replay. Storage changes need traversal, size, corruption, and
redaction tests.

Run:

```bash
python -m pytest
python -m ruff check .
python -m mypy
python scripts/security_check.py
python scripts/killer_demo.py
```

Additional adapters, arbitrary predicate languages, a server, a hosted trace
store, and a browser UI remain out of scope for this pre-0.1 seed.

Format changes follow `docs/format-compatibility.md`. Release changes follow
`RELEASING.md` and require an architecture decision when they affect a public
contract.
