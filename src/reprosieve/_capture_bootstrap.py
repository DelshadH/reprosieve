from __future__ import annotations

import base64
import json
import os
from typing import Any

from .adapters.openai_agents import ReproSieveTraceProcessor, install_processor

_PROCESSOR: ReproSieveTraceProcessor | None = None
_MAX_CONFIG_BYTES = 1024 * 1024


def _string_tuple(value: Any, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"capture {label} is invalid")
    return tuple(value)


def install_from_environment() -> ReproSieveTraceProcessor:
    global _PROCESSOR
    encoded = os.environ.pop("RUNSIEVE_CAPTURE_CONFIG_B64", "")
    if not encoded or len(encoded) > _MAX_CONFIG_BYTES * 2:
        raise ValueError("capture configuration is missing or too large")
    try:
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > _MAX_CONFIG_BYTES:
            raise ValueError("capture configuration is too large")
        value = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("capture configuration is invalid") from error
    if not isinstance(value, dict):
        raise ValueError("capture configuration must be an object")
    expected = {
        "allow_paths",
        "deny_paths",
        "environment_names",
        "exact_canaries",
        "max_events",
        "output_path",
        "patterns",
        "retain_existing",
        "workspace_paths",
        "workspace_root",
    }
    if set(value) != expected:
        raise ValueError("capture configuration fields are invalid")
    if not isinstance(value["output_path"], str) or not isinstance(value["workspace_root"], str):
        raise ValueError("capture paths are invalid")
    if isinstance(value["max_events"], bool) or not isinstance(value["max_events"], int):
        raise ValueError("capture event limit is invalid")
    if not isinstance(value["retain_existing"], bool):
        raise ValueError("capture exporter policy is invalid")
    processor = ReproSieveTraceProcessor(
        output_path=value["output_path"],
        exact_canaries=_string_tuple(value["exact_canaries"], label="canaries"),
        patterns=_string_tuple(value["patterns"], label="patterns"),
        allow_paths=_string_tuple(value["allow_paths"], label="allow paths"),
        deny_paths=_string_tuple(value["deny_paths"], label="deny paths"),
        workspace_root=value["workspace_root"],
        workspace_paths=_string_tuple(value["workspace_paths"], label="workspace paths"),
        environment_names=_string_tuple(value["environment_names"], label="environment names"),
        max_events=value["max_events"],
    )
    install_processor(processor, retain_existing=value["retain_existing"])
    _PROCESSOR = processor
    return processor
