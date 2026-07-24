from __future__ import annotations

import unittest

from runsieve.schema import Capsule, Event, validate_capsule


class SchemaTests(unittest.TestCase):
    def test_missing_dependency_is_rejected(self) -> None:
        capsule = Capsule(
            schema_version="1",
            trace_id="trace",
            events=(Event("e1", "tool_result", None, 1, {}, ("missing",)),),
            metadata={},
        )
        with self.assertRaises(ValueError):
            validate_capsule(capsule)


if __name__ == "__main__":
    unittest.main()
