from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from typing import Any

from scripts.gates._verify import GateSpec, pytest_measurement, verify_gate

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = "src/runsieve/adapters/openai_agents.py"


def scan_sdk_imports(source: bytes) -> tuple[str, ...]:
    try:
        tree = ast.parse(source.decode("utf-8"))
    except (SyntaxError, UnicodeDecodeError) as error:
        raise ValueError("RS-G01 adapter source is not valid Python") from error
    violations: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            modules = [module]
            if module == "agents":
                modules.extend(
                    f"agents.{alias.name}"
                    for alias in node.names
                    if alias.name.startswith("_")
                )
        else:
            continue
        for module in modules:
            parts = module.split(".")
            if parts and parts[0] == "agents" and any(
                part.startswith("_") for part in parts[1:]
            ):
                violations.add(module)
    return tuple(sorted(violations))


def _validate_rs_g01(
    manifest: dict[str, Any],
    _proof: dict[str, Any],
    _base: Path,
) -> set[str]:
    current = (ROOT / ADAPTER).read_bytes()
    committed = subprocess.run(
        ["git", "show", f"{manifest['commit']}:{ADAPTER}"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if committed.returncode != 0 or committed.stdout != current:
        raise ValueError("RS-G01 adapter differs from the measured evidence commit")
    violations = scan_sdk_imports(committed.stdout)
    if violations:
        raise ValueError(f"RS-G01 adapter uses private SDK imports: {', '.join(violations)}")
    return set(SPEC.assertions)


SPEC = GateSpec(
    gate="RS-G01",
    measurements=(
        pytest_measurement(
            (
                "public-processor-only",
                "default-exporter-replaced",
                "no-duplicate-export",
                "sdk-private-import-scan",
                "synthetic-trace-captured",
            ),
            "tests/test_openai_adapter.py",
        ),
    ),
    expected_support_sha256="0487c43e903dbd2621b94e982dd02c2ad77b319311ad6401c4fcfee9b7a7fc90",
    extra_validator=_validate_rs_g01,
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
