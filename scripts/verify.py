from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tomllib
from pathlib import Path

from scripts.contract import load_project_documents

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "AGENTS.md", "CODEX_START.txt", "CODEX_TASKS.json", "CONTRACT_VERSION.json", "GATE_REGISTRY.json", "PROGRESS.json",
    "MANUAL_REQUIRED.json", "WORKLOG.md", "docs/PRODUCT_CONTRACT.md", "docs/ARCHITECTURE.md", "docs/PRIVACY.md", "docs/CONTROL_PLANE.md",
    "docs/PROOF_GATES.md", "docs/EVIDENCE_CONTRACT.md", "scripts/bootstrap.py", "scripts/contract_self_test.py",
    "src/runsieve/ddmin.py", "src/runsieve/adapters/openai_agents.py",
]

def main() -> int:
    for relative in REQUIRED:
        if not (ROOT / relative).is_file():
            raise RuntimeError(f"missing required file: {relative}")
    tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    docs = load_project_documents(ROOT, "runsieve")
    for gate in docs["registry"]["gates"]:
        argv = gate["argv"]
        if len(argv) != 3 or argv[:2] != ["python", "-m"] or not argv[2].startswith("scripts.gates.RS_G"):
            raise RuntimeError(f"{gate['id']}: verifier must be a repository-owned Python module")
        module_path = ROOT / (argv[2].replace(".", "/") + ".py")
        if not module_path.is_file():
            raise RuntimeError(f"{gate['id']}: missing verifier module {module_path.relative_to(ROOT)}")
    contract = subprocess.run([sys.executable, "-m", "scripts.contract_self_test"], cwd=ROOT, check=False)
    if contract.returncode:
        return contract.returncode
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    compile_result = subprocess.run([sys.executable, "-m", "compileall", "-q", "src", "scripts", "tests"], cwd=ROOT, env=env, check=False)
    if compile_result.returncode:
        return compile_result.returncode
    test_argv = [sys.executable, "-m", "pytest", "-q"] if importlib.util.find_spec("pytest") is not None else [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
    tests = subprocess.run(test_argv, cwd=ROOT, env=env, check=False)
    if tests.returncode:
        return tests.returncode
    optional_checks = [
        ("ruff", [sys.executable, "-m", "ruff", "check", "."]),
        ("mypy", [sys.executable, "-m", "mypy"]),
    ]
    for module, argv in optional_checks:
        if importlib.util.find_spec(module) is not None:
            result = subprocess.run(argv, cwd=ROOT, env=env, check=False)
            if result.returncode:
                return result.returncode
    print("RunSieve autonomous-build contract and reference kernel are structurally valid. Product release remains governed by python -m scripts.release_gate.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
