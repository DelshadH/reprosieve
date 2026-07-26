from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r"^[0-9a-f]{40}$")


def expected_tag() -> str:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    version = project.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("project version is invalid")
    return f"v{version}"


def _git(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if completed.returncode:
        raise ValueError(f"git {' '.join(arguments)} failed")
    return completed.stdout.strip()


def verify_release_ref(tag: str, *, canonical_ref: str = "origin/main") -> str:
    if tag != expected_tag():
        raise ValueError(f"release tag must be exactly {expected_tag()}")
    tag_ref = f"refs/tags/{tag}"
    if _git("cat-file", "-t", tag_ref) != "tag":
        raise ValueError("release tag must be annotated")
    target = _git("rev-parse", f"{tag_ref}^{{}}")
    head = _git("rev-parse", "HEAD")
    canonical = _git("rev-parse", canonical_ref)
    if any(SHA.fullmatch(value) is None for value in (target, head, canonical)):
        raise ValueError("release ref identity is invalid")
    if target != head or target != canonical:
        raise ValueError("release tag must target the exact canonical main head")
    return target


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        print("usage: python -m scripts.release_preflight TAG", file=sys.stderr)
        return 2
    try:
        commit = verify_release_ref(arguments[0])
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        print(f"release preflight failed: {error}", file=sys.stderr)
        return 1
    print(f"release preflight passed for {arguments[0]} at {commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
