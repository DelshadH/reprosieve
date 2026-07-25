from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

_FILE_ATTRIBUTE_REPARSE_POINT = 0x0400


def is_link_like(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT
    )


def _reject_link_ancestors(path: Path, *, label: str) -> Path:
    absolute = Path(os.path.abspath(path))
    temp_root = Path(os.path.abspath(tempfile.gettempdir()))
    candidates = (absolute, *absolute.parents)
    for candidate in candidates:
        trusted_temp_prefix = candidate == temp_root or candidate in temp_root.parents
        if candidate.exists() and is_link_like(candidate) and not trusted_temp_prefix:
            raise ValueError(f"{label} must not use symlink or junction components")
    return absolute


def ensure_real_directory(path: str | Path, *, label: str) -> Path:
    absolute = _reject_link_ancestors(Path(path), label=label)
    if not absolute.is_dir():
        raise ValueError(f"{label} must be an existing directory")
    return absolute


def ensure_regular_file(path: str | Path, *, label: str) -> Path:
    absolute = _reject_link_ancestors(Path(path), label=label)
    if not absolute.is_file():
        raise ValueError(f"{label} must be a regular file")
    return absolute


def ensure_new_path(path: str | Path, *, label: str) -> Path:
    absolute = Path(os.path.abspath(path))
    if is_link_like(absolute):
        raise ValueError(f"{label} must not be a symlink or junction")
    if absolute.exists():
        raise FileExistsError(f"{label} already exists")
    ensure_real_directory(absolute.parent, label=f"{label} parent")
    return absolute
