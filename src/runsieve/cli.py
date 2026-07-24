from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="runsieve",
        description="Pre-release CLI for minimizing failed agent runs into offline reproductions.",
    )
    subparsers = parser.add_subparsers(dest="command")
    for name in ("capture", "minimize", "replay", "export", "verify-minimal"):
        subparsers.add_parser(name, help=f"Planned command: {name}")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return 0
    parser.error(f"{args.command!r} is not available in this pre-release build")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
