from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="runsieve",
        description="Implementation skeleton: minimize failed agent runs into hermetic reproductions.",
    )
    subparsers = parser.add_subparsers(dest="command")
    for name in ("capture", "minimize", "replay", "export", "verify-minimal"):
        subparsers.add_parser(name, help=f"Target command; not implemented before its CODEX task: {name}")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return 0
    parser.error(f"{args.command!r} is not implemented; execute CODEX_TASKS.json in order")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
