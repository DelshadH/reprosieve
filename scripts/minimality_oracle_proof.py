from __future__ import annotations

import json
from typing import Any

from reprosieve.fixtures import killer_capsule, killer_predicate
from reprosieve.hierarchy import minimize_capsule
from reprosieve.schema import Capsule, JsonValue
from reprosieve.verify import verify_one_minimal

_CHUNK = 32


def _walk_paths(
    value: JsonValue,
    *,
    target: type[str | int] | None,
) -> list[tuple[str | int, ...]]:
    paths: list[tuple[str | int, ...]] = []

    def walk(current: JsonValue, path: tuple[str | int, ...]) -> None:
        if isinstance(current, str):
            if target is None:
                paths.append(path)
            return
        if isinstance(current, dict):
            if current.get("$reprosieve_redacted") is True:
                return
            for key, child in current.items():
                if target is str:
                    paths.append((*path, key))
                walk(child, (*path, key))
        elif isinstance(current, list):
            for index, child in enumerate(current):
                if target is int:
                    paths.append((*path, index))
                walk(child, (*path, index))

    walk(value, ())
    return paths


def enumerate_final_units(capsule: Capsule) -> list[str]:
    units: list[str] = []
    units.extend(f"event:{event.id}" for event in capsule.events if event.kind != "run")
    for event in capsule.events:
        for category, target in (("json_field", str), ("json_item", int)):
            units.extend(
                f"{category}:{event.id}:{path!r}"
                for path in _walk_paths(event.payload, target=target)
            )
        for path in _walk_paths(event.payload, target=None):
            current: JsonValue = event.payload
            for part in path:
                current = current[part]  # type: ignore[index]
            if not isinstance(current, str):
                raise AssertionError("text oracle path did not resolve to text")
            count = (len(current) + _CHUNK - 1) // _CHUNK
            units.extend(
                f"text_chunk:{event.id}:{path!r}:{index}"
                for index in range(count)
            )
    for name, content in capsule.workspace.items():
        units.append(f"file:{name}")
        count = (len(content) + _CHUNK - 1) // _CHUNK
        units.extend(f"file_chunk:{name}:{index}" for index in range(count))
    units.extend(f"environment:{name}" for name in capsule.environment)
    return units


def validate_oracle_document(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "attempted_units",
        "exact_unit_coverage",
        "expected_units",
        "is_one_minimal",
        "reduced_events",
        "reproducing_deletions",
        "schema_version",
        "source_events",
    }:
        raise ValueError("minimality oracle document has invalid fields")
    expected = value["expected_units"]
    attempted = value["attempted_units"]
    if (
        value["schema_version"] != 1
        or value["source_events"] != 247
        or not isinstance(value["reduced_events"], int)
        or isinstance(value["reduced_events"], bool)
        or not 1 <= value["reduced_events"] <= 10
        or not isinstance(expected, list)
        or not expected
        or any(not isinstance(unit, str) or not unit for unit in expected)
        or len(expected) != len(set(expected))
        or not isinstance(attempted, list)
        or any(not isinstance(unit, str) or not unit for unit in attempted)
        or len(attempted) != len(set(attempted))
        or attempted != expected
        or value["exact_unit_coverage"] is not True
        or value["is_one_minimal"] is not True
        or value["reproducing_deletions"] != []
    ):
        raise ValueError("minimality oracle did not prove exact one-unit coverage")
    return value


def build_proof() -> dict[str, Any]:
    source = killer_capsule()
    reduced = minimize_capsule(source, killer_predicate).capsule
    proof = verify_one_minimal(reduced, killer_predicate)
    expected = enumerate_final_units(reduced)
    document: dict[str, Any] = {
        "attempted_units": [attempt.unit for attempt in proof.attempts],
        "exact_unit_coverage": [attempt.unit for attempt in proof.attempts] == expected,
        "expected_units": expected,
        "is_one_minimal": proof.is_one_minimal,
        "reduced_events": len(reduced.events),
        "reproducing_deletions": list(proof.reproducing_deletions),
        "schema_version": 1,
        "source_events": len(source.events),
    }
    return validate_oracle_document(document)


def main() -> int:
    print(json.dumps(build_proof(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
