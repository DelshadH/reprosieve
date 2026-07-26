from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{40}$")


def verify_receipt(path: Path, *, expected_commit: str) -> dict[str, object]:
    if SHA.fullmatch(expected_commit) is None:
        raise ValueError("expected final-evidence commit is invalid")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("final-evidence receipt is invalid JSON") from error
    if (
        not isinstance(value, dict)
        or set(value) != {"commit", "gate", "passed", "workflow_run"}
        or value.get("commit") != expected_commit
        or value.get("gate") != "final-release-evidence"
        or value.get("passed") is not True
        or not isinstance(value.get("workflow_run"), str)
        or not value["workflow_run"]
    ):
        raise ValueError("final-evidence receipt does not bind the expected commit")
    return value


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 2:
        print(
            "usage: python -m scripts.verify_final_receipt RECEIPT EXPECTED_COMMIT",
            file=sys.stderr,
        )
        return 2
    try:
        receipt = verify_receipt(Path(arguments[0]), expected_commit=arguments[1])
    except ValueError as error:
        print(f"final-evidence receipt verification failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
