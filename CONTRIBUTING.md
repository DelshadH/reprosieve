# Contributing

RunSieve handles data that may contain credentials, source code, and personal
information. Read `docs/privacy.md` and `docs/architecture.md` before changing
capture, storage, replay, or export behavior.

Keep pull requests narrow and begin with a failing fixture. Reducer changes need
an independent 1-minimality check. Replay changes need a proof that no model
provider or original external tool was called. Storage changes need traversal,
size, corruption, and redaction tests.

Run:

```bash
python -m pytest
python -m ruff check .
python -m mypy
```

Additional frameworks, a server, a hosted trace store, and a browser UI are out
of scope until the core command-line workflow is complete.
