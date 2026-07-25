from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from typing import Any

from scripts.gates._verify import (
    GateSpec,
    pytest_measurement,
    require_pytest_pass,
    verify_gate,
)

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
    base: Path,
) -> set[str]:
    assertions: set[str] = set()
    for index, assertion in enumerate(
        (
            "public-processor-only",
            "default-exporter-replaced",
            "no-duplicate-export",
        )
    ):
        require_pytest_pass(manifest, base, index)
        assertions.add(assertion)
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
    require_pytest_pass(manifest, base, 3)
    assertions.add("sdk-private-import-scan")
    require_pytest_pass(manifest, base, 4)
    assertions.add("synthetic-trace-captured")
    return assertions


SPEC = GateSpec(
    gate="RS-G01",
    measurements=(
        pytest_measurement(
            ("public-processor-only",),
            "tests/test_openai_adapter.py::test_public_processor_captures_real_sdk_spans_without_duplicate_export",
        ),
        pytest_measurement(
            ("default-exporter-replaced",),
            "tests/test_openai_adapter.py::test_public_processor_captures_real_sdk_spans_without_duplicate_export",
        ),
        pytest_measurement(
            ("no-duplicate-export",),
            "tests/test_openai_adapter.py::test_public_processor_captures_real_sdk_spans_without_duplicate_export",
        ),
        pytest_measurement(
            ("sdk-private-import-scan",),
            "tests/test_gate_verifiers.py::test_rs_g01_scans_the_committed_adapter_for_private_sdk_imports",
        ),
        pytest_measurement(
            ("synthetic-trace-captured",),
            "tests/test_openai_adapter.py::test_public_processor_captures_real_sdk_spans_without_duplicate_export",
        ),
    ),
    expected_support_sha256="c61b33ff9852dcde50c1204e083426b3b52e17fb922a4b7b8317c0f16a7c698d",
    extra_validator=_validate_rs_g01,
)

if __name__ == "__main__":
    raise SystemExit(verify_gate(SPEC))
