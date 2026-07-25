from __future__ import annotations

import json
from pathlib import Path

from runsieve.capsule import canonical_json
from runsieve.replay import offline_replay
from tests.helpers import sample_capsule

ROOT = Path(__file__).resolve().parents[1]


def test_machine_readable_schema_catalog_is_well_formed() -> None:
    names = {
        "capsule-v1.schema.json",
        "materialization-v1.schema.json",
        "predicate-report-v1.schema.json",
        "reduction-report-v1.schema.json",
    }
    paths = {path.name: path for path in (ROOT / "schemas").glob("*.json")}
    assert set(paths) == names
    for name in sorted(names):
        document = json.loads(paths[name].read_text(encoding="utf-8"))
        assert document["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert document["$id"].endswith(f"/schemas/{name}")
        assert document["type"] == "object"
        assert document["title"].startswith("RunSieve")


def test_materialization_matches_the_versioned_golden_artifact() -> None:
    actual = canonical_json(offline_replay(sample_capsule()).to_json())
    expected = (ROOT / "tests" / "golden" / "materialization-v1.json").read_bytes()
    assert actual == expected
