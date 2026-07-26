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


def read_regular_file_bounded(
    path: str | Path,
    *,
    max_bytes: int,
    label: str,
) -> bytes:
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 0:
        raise ValueError(f"{label} size limit is invalid")
    absolute = _reject_link_ancestors(Path(path), label=label)
    before: dict[Path, tuple[int, int, int, int]] = {}
    for candidate in (absolute, *absolute.parents):
        try:
            metadata = candidate.lstat()
        except OSError:
            continue
        before[candidate] = (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            getattr(metadata, "st_file_attributes", 0),
        )
    flags = os.O_RDONLY
    for name in ("O_BINARY", "O_CLOEXEC", "O_NOINHERIT", "O_NOFOLLOW"):
        flags |= int(getattr(os, name, 0))
    try:
        descriptor = os.open(absolute, flags)
    except OSError as error:
        raise ValueError(f"{label} could not be opened safely") from error
    try:
        opened = os.fstat(descriptor)
        after: dict[Path, tuple[int, int, int, int]] = {}
        for candidate in before:
            try:
                metadata = candidate.lstat()
            except OSError as error:
                raise ValueError(f"{label} changed while it was opened") from error
            after[candidate] = (
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_mode,
                getattr(metadata, "st_file_attributes", 0),
            )
        if after != before or any(is_link_like(candidate) for candidate in before):
            raise ValueError(f"{label} changed while it was opened")
        current = os.stat(absolute, follow_symlinks=False)
        if (
            not stat.S_ISREG(opened.st_mode)
            or stat.S_ISLNK(current.st_mode)
            or bool(
                getattr(current, "st_file_attributes", 0)
                & _FILE_ATTRIBUTE_REPARSE_POINT
            )
        ):
            raise ValueError(f"{label} must be a regular file")
        if (
            opened.st_ino
            and current.st_ino
            and (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
        ):
            raise ValueError(f"{label} changed while it was opened")
        if opened.st_size > max_bytes:
            raise ValueError(f"{label} size limit exceeded")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > max_bytes:
            raise ValueError(f"{label} size limit exceeded")
        return data
    except OSError as error:
        raise ValueError(f"{label} could not be read safely") from error
    finally:
        os.close(descriptor)


def ensure_new_path(path: str | Path, *, label: str) -> Path:
    absolute = Path(os.path.abspath(path))
    if is_link_like(absolute):
        raise ValueError(f"{label} must not be a symlink or junction")
    if absolute.exists():
        raise FileExistsError(f"{label} already exists")
    ensure_real_directory(absolute.parent, label=f"{label} parent")
    return absolute
