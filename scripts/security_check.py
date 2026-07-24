from __future__ import annotations

import ast
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTION = re.compile(r"^\s*-\s+uses:\s+([^@\s]+)@([^\s#]+)", re.MULTILINE)
SECRET_PATTERNS = {
    "OpenAI-style key": re.compile(rb"\bsk-[A-Za-z0-9_-]{24,}\b"),
    "GitHub token": re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "AWS access key": re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    "private key": re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}


def tracked_files() -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [
        ROOT / item.decode("utf-8")
        for item in completed.stdout.split(b"\0")
        if item
    ]


def check_actions(paths: list[Path], errors: list[str]) -> None:
    for path in paths:
        if path.suffix not in {".yml", ".yaml"} or ".github/workflows" not in path.as_posix():
            continue
        text = path.read_text(encoding="utf-8")
        for action, reference in ACTION.findall(text):
            if action.startswith("./"):
                continue
            if not re.fullmatch(r"[0-9a-f]{40}", reference):
                errors.append(f"{path.relative_to(ROOT)}: unpinned action {action}")


def call_name(call: ast.Call) -> str:
    node = call.func
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def check_python(paths: list[Path], errors: list[str]) -> None:
    for path in paths:
        if path.suffix != ".py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = call_name(node)
            if name in {"eval", "exec", "os.system"}:
                errors.append(f"{path.relative_to(ROOT)}:{node.lineno}: unsafe execution primitive")
            if name.startswith("subprocess."):
                for keyword in node.keywords:
                    if (
                        keyword.arg == "shell"
                        and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value is True
                    ):
                        errors.append(
                            f"{path.relative_to(ROOT)}:{node.lineno}: shell=True is forbidden"
                        )


def contains_secret_pattern(paths: list[Path]) -> bool:
    for path in paths:
        if not path.is_file() or path.stat().st_size > 5 * 1024 * 1024:
            continue
        payload = path.read_bytes()
        for pattern in SECRET_PATTERNS.values():
            if pattern.search(payload):
                return True
    return False


def check_audit_requirements(errors: list[str]) -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    expected = set(project["project"]["optional-dependencies"]["dev"])
    actual = {
        line.strip()
        for line in (ROOT / "requirements-audit.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    if expected != actual:
        errors.append(
            "requirements-audit.txt must exactly match project.optional-dependencies.dev "
            f"(missing={sorted(expected - actual)}, extra={sorted(actual - expected)})"
        )


def main() -> int:
    paths = tracked_files()
    errors: list[str] = []
    check_audit_requirements(errors)
    check_actions(paths, errors)
    check_python(paths, errors)
    secret_pattern_found = contains_secret_pattern(paths)
    if errors:
        for error in sorted(errors):
            print(error, file=sys.stderr)
        return 1
    if secret_pattern_found:
        print("possible secret pattern detected", file=sys.stderr)
        return 1
    print(f"security policy checks passed for {len(paths)} tracked files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
