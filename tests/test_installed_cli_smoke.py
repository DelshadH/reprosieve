from __future__ import annotations

import importlib.util


def test_installed_cli_smoke_runner_is_packaging_owned() -> None:
    spec = importlib.util.find_spec("scripts.installed_cli_smoke")
    assert spec is not None
