from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

_SECRET_KEY = re.compile(
    r"(?:token|secret|password|passwd|authorization|cookie|api[_-]?key|private[_-]?key|session)",
    re.IGNORECASE,
)
_TOKEN_VALUE = re.compile(
    r"(?:Bearer\s+[A-Za-z0-9._~+/=-]{8,}|sk-[A-Za-z0-9_-]{12,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)",
    re.IGNORECASE,
)


def _marker(value: str, salt: bytes) -> str:
    digest = hashlib.sha256(salt + value.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"<redacted:{digest}>"


def redact(value: Any, *, salt: bytes, key: str | None = None) -> Any:
    """Recursively redact common secret keys and token-shaped string material.

    RS-020 must extend this with bounded traversal, explicit user patterns,
    before-disk logging guards, and byte-scan proof fixtures.
    """
    if key is not None and _SECRET_KEY.search(key):
        return _marker(str(value), salt)
    if isinstance(value, str):
        return _TOKEN_VALUE.sub(lambda match: _marker(match.group(0), salt), value)
    if isinstance(value, Mapping):
        return {str(child_key): redact(child, salt=salt, key=str(child_key)) for child_key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [redact(child, salt=salt) for child in value]
    return value
