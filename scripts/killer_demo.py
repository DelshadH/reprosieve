from __future__ import annotations

from reprosieve.cli import main


def run() -> int:
    """Keep the historical release-gate entry point aligned with the installed CLI."""
    return main(["demo"])


if __name__ == "__main__":
    raise SystemExit(run())
