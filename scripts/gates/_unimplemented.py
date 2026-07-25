from __future__ import annotations

import sys

def unimplemented(gate: str) -> None:
    print(f"{gate} verifier is intentionally unimplemented. Implement the real proof owned by CODEX_TASKS.json; never replace this with a constant-pass stub.", file=sys.stderr)
    raise SystemExit(64)
