# Dependency review

Review date: 2026-07-24.

The ReproSieve core has no runtime dependencies. It uses Python's standard library
for archives, hashing, subprocesses, replay, reduction, validation, and export.

The optional `openai` extra installs `openai-agents>=0.18.3,<0.19`. Version
0.18.3 was the current signed PyPI release at review time, requires Python 3.10
or newer, publishes provenance from `openai/openai-agents-python`, and is MIT
licensed. It is imported only by capture bootstrap and adapter code.

Development dependencies are exact-pinned in `pyproject.toml`:

- Hatchling and Build for PEP 517 packages;
- Pytest, pytest-cov, and Hypothesis for tests;
- Ruff and mypy for static checks;
- pip-audit for vulnerability data;
- Bandit for high-severity source findings;
- detect-secrets with an audited false-positive baseline; CI checks all repository
  files through `detect-secrets-hook` and fails on findings absent from that baseline;
- pip-licenses for the transitive license inventory;
- openai-agents 0.18.3 for the real public-processor fixture.

The release environment runs:

```bash
python -m pip_audit --strict --requirement requirements-audit.txt
python -m bandit -q -r src -lll
python scripts/security_check.py
pip-licenses --format=markdown --with-urls
```

No package performs an install-time project hook; installation uses standard
wheel metadata. The wheel smoke test installs ReproSieve with `--no-deps`, proving
the core command can start without the optional SDK dependency.
