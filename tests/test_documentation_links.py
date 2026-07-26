from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
_MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def _repository_markdown() -> list[Path]:
    return sorted(
        [
            *ROOT.glob("*.md"),
            *(ROOT / "docs").rglob("*.md"),
        ]
    )


def _relative_parts(source: Path, target: str) -> tuple[str, ...] | None:
    value = target.removeprefix("<").removesuffix(">")
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    parts = list(source.parent.relative_to(ROOT).parts)
    for part in PurePosixPath(unquote(parsed.path)).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                raise AssertionError(f"{source}: link escapes repository: {target}")
            parts.pop()
        else:
            parts.append(part)
    return tuple(parts)


def _exact_path_exists(parts: tuple[str, ...]) -> bool:
    current = ROOT
    for part in parts:
        names = {entry.name for entry in current.iterdir()}
        if part not in names:
            return False
        current /= part
    return current.exists()


def test_local_markdown_links_exist_with_exact_case() -> None:
    failures: list[str] = []
    for source in _repository_markdown():
        text = source.read_text(encoding="utf-8")
        for target in _MARKDOWN_LINK.findall(text):
            parts = _relative_parts(source, target)
            if parts is not None and not _exact_path_exists(parts):
                failures.append(
                    f"{source.relative_to(ROOT).as_posix()} -> {target}"
                )
    assert failures == []
