from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .schema import JsonValue

_SECRET_KEY = re.compile(
    r"(?:token|secret|password|passwd|authorization|cookie|api[_-]?key|private[_-]?key|session)",
    re.IGNORECASE,
)
_TOKEN_VALUE = re.compile(
    r"(?:"
    r"(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{8,}"
    r"|sk-[A-Za-z0-9_-]{12,}"
    r"|(?:gh[pousr]_[A-Za-z0-9]{20,})"
    r"|(?:xox[baprs]-[A-Za-z0-9-]{10,})"
    r"|(?:AKIA[0-9A-Z]{16})"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
    r")",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class RedactionLimits:
    max_depth: int = 64
    max_nodes: int = 250_000
    max_string_bytes: int = 4 * 1024 * 1024
    max_patterns: int = 64


@dataclass(frozen=True, slots=True)
class RedactionPolicy:
    salt: bytes
    exact_canaries: tuple[str, ...] = ()
    patterns: tuple[str, ...] = ()
    allow_paths: tuple[str, ...] = ()
    deny_paths: tuple[str, ...] = ()
    limits: RedactionLimits = field(default_factory=RedactionLimits)


@dataclass(frozen=True, slots=True)
class RedactionReport:
    replacements: int
    reasons: dict[str, int]
    scanned_nodes: int

    def to_json(self) -> dict[str, JsonValue]:
        return {
            "replacements": self.replacements,
            "reasons": dict(sorted(self.reasons.items())),
            "scanned_nodes": self.scanned_nodes,
        }


def _fingerprint(value: object, salt: bytes) -> str:
    if isinstance(value, bytes):
        payload = value
    else:
        payload = str(value).encode("utf-8", errors="replace")
    return hashlib.sha256(b"runsieve-redaction-v1\0" + salt + b"\0" + payload).hexdigest()[:20]


def _typed_marker(value: object, salt: bytes) -> dict[str, JsonValue]:
    type_name = "null" if value is None else type(value).__name__
    return {
        "$runsieve_redacted": True,
        "fingerprint": _fingerprint(value, salt),
        "type": type_name,
    }


def _path_matches(path: str, configured: tuple[str, ...]) -> bool:
    return any(path == item or path.startswith((f"{item}.", f"{item}[")) for item in configured)


class _Redactor:
    def __init__(self, policy: RedactionPolicy) -> None:
        if not policy.salt:
            raise ValueError("redaction salt must not be empty")
        if len(policy.patterns) > policy.limits.max_patterns:
            raise ValueError("redaction pattern limit exceeded")
        try:
            self.patterns = tuple(_compile_user_pattern(item) for item in policy.patterns)
        except re.error as error:
            raise ValueError("invalid redaction pattern") from error
        self.policy = policy
        self.nodes = 0
        self.replacements = 0
        self.reasons: dict[str, int] = {}
        self.active: set[int] = set()

    def _record(self, reason: str) -> None:
        self.replacements += 1
        self.reasons[reason] = self.reasons.get(reason, 0) + 1

    def _replace_text(self, text: str) -> str:
        if len(text.encode("utf-8")) > self.policy.limits.max_string_bytes:
            raise ValueError("redaction string limit exceeded")
        result = text
        for canary in self.policy.exact_canaries:
            if not canary:
                continue
            if canary in result:
                marker = f"<redacted:{_fingerprint(canary, self.policy.salt)}>"
                count = result.count(canary)
                result = result.replace(canary, marker)
                for _ in range(count):
                    self._record("exact_canary")
        for pattern in self.patterns:
            def replace_user(match: re.Match[str]) -> str:
                self._record("user_pattern")
                return f"<redacted:{_fingerprint(match.group(0), self.policy.salt)}>"

            result = pattern.sub(replace_user, result)

        def replace_token(match: re.Match[str]) -> str:
            self._record("token_shape")
            return f"<redacted:{_fingerprint(match.group(0), self.policy.salt)}>"

        return _TOKEN_VALUE.sub(replace_token, result)

    def visit(self, value: object, *, path: str, key: str | None, depth: int) -> JsonValue:
        self.nodes += 1
        if self.nodes > self.policy.limits.max_nodes:
            raise ValueError("redaction node limit exceeded")
        if depth > self.policy.limits.max_depth:
            raise ValueError("redaction depth limit exceeded")

        is_denied = bool(path and _path_matches(path, self.policy.deny_paths))
        is_allowed = bool(path and _path_matches(path, self.policy.allow_paths))
        if is_denied or (key is not None and _SECRET_KEY.search(key) and not is_allowed):
            self._record("deny_path" if is_denied else "secret_key")
            return _typed_marker(value, self.policy.salt)

        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            return self._replace_text(value)
        if isinstance(value, bytes):
            decoded = value.decode("utf-8", errors="replace")
            replaced = self._replace_text(decoded)
            if replaced != decoded:
                return replaced
            self._record("binary")
            return _typed_marker(value, self.policy.salt)
        if isinstance(value, Mapping):
            identity = id(value)
            if identity in self.active:
                raise ValueError("redaction input contains a cycle")
            self.active.add(identity)
            output: dict[str, JsonValue] = {}
            try:
                for raw_key, child in value.items():
                    child_key = self._replace_text(str(raw_key))
                    if child_key in output:
                        raise ValueError("redaction produced duplicate object keys")
                    child_path = f"{path}.{child_key}" if path else child_key
                    output[child_key] = self.visit(
                        child,
                        path=child_path,
                        key=child_key,
                        depth=depth + 1,
                    )
            finally:
                self.active.remove(identity)
            return output
        if isinstance(value, Sequence):
            identity = id(value)
            if identity in self.active:
                raise ValueError("redaction input contains a cycle")
            self.active.add(identity)
            output_list: list[JsonValue] = []
            try:
                for index, child in enumerate(value):
                    child_path = f"{path}[{index}]" if path else f"[{index}]"
                    output_list.append(
                        self.visit(child, path=child_path, key=None, depth=depth + 1)
                    )
            finally:
                self.active.remove(identity)
            return output_list
        self._record("unsupported_type")
        return _typed_marker(value, self.policy.salt)


def _quantifier_count(pattern: str) -> int:
    count = 0
    escaped = False
    in_character_class = False
    for character in pattern:
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "[" and not in_character_class:
            in_character_class = True
        elif character == "]" and in_character_class:
            in_character_class = False
        elif not in_character_class and character in "*+?":
            count += 1
    return count


def _compile_user_pattern(pattern: str) -> re.Pattern[str]:
    """Compile a conservative, bounded subset of regular expressions.

    The standard-library engine has no timeout, so grouping, alternation, counted
    repetitions, backreferences, and multiple unbounded wildcards are rejected.
    """
    if (
        not pattern
        or len(pattern.encode("utf-8")) > 256
        or any(character in pattern for character in "()|{}")
        or re.search(r"\\[1-9]", pattern)
        or _quantifier_count(pattern) > 1
    ):
        raise re.error("pattern is outside the bounded subset")
    return re.compile(pattern)


def redact_with_report(
    value: object,
    *,
    policy: RedactionPolicy,
) -> tuple[JsonValue, RedactionReport]:
    redactor = _Redactor(policy)
    result = redactor.visit(value, path="", key=None, depth=0)
    report = RedactionReport(
        replacements=redactor.replacements,
        reasons=dict(sorted(redactor.reasons.items())),
        scanned_nodes=redactor.nodes,
    )
    return result, report


def redact(value: Any, *, salt: bytes, key: str | None = None) -> Any:
    policy = RedactionPolicy(salt=salt)
    redactor = _Redactor(policy)
    return redactor.visit(value, path=key or "", key=key, depth=0)
