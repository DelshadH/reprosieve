from __future__ import annotations

import unittest

from reprosieve.schema import Capsule, Event, SchemaLimits, validate_capsule


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

    def test_tool_result_requires_exactly_one_tool_call(self) -> None:
        capsule = Capsule(
            schema_version="1",
            trace_id="trace",
            events=(
                Event("run", "run", None, 0, {}),
                Event("not-a-call", "unknown", "run", 1, {}),
                Event("result", "tool_result", "run", 2, {}, ("not-a-call",)),
            ),
            metadata={},
        )
        with self.assertRaisesRegex(ValueError, "tool call"):
            validate_capsule(capsule)

    def test_model_response_requires_request_dependency(self) -> None:
        capsule = Capsule(
            schema_version="1",
            trace_id="trace",
            events=(
                Event("run", "run", None, 0, {}),
                Event("response", "model_response", "run", 1, {"output": "x"}),
            ),
            metadata={},
        )
        with self.assertRaisesRegex(ValueError, "model request"):
            validate_capsule(capsule)

    def test_rejects_unsupported_version_unsafe_workspace_and_environment(self) -> None:
        base = Capsule(
            schema_version="1",
            trace_id="trace",
            events=(Event("run", "run", None, 0, {}),),
            metadata={},
        )
        with self.assertRaisesRegex(ValueError, "schema"):
            validate_capsule(
                Capsule(
                    schema_version="2",  # type: ignore[arg-type]
                    trace_id=base.trace_id,
                    events=base.events,
                    metadata={},
                )
            )
        with self.assertRaisesRegex(ValueError, "workspace"):
            validate_capsule(
                Capsule(
                    schema_version="1",
                    trace_id=base.trace_id,
                    events=base.events,
                    metadata={},
                    workspace={"../escape.py": "pass"},
                )
            )
        with self.assertRaisesRegex(ValueError, "environment"):
            validate_capsule(
                Capsule(
                    schema_version="1",
                    trace_id=base.trace_id,
                    events=base.events,
                    metadata={},
                    environment={"BAD=NAME": "x"},
                )
            )

    def test_enforces_event_and_recursion_limits(self) -> None:
        capsule = Capsule(
            schema_version="1",
            trace_id="trace",
            events=tuple(Event(f"e{i}", "unknown", None, i, {}) for i in range(3)),
            metadata={},
        )
        with self.assertRaisesRegex(ValueError, "event limit"):
            validate_capsule(capsule, limits=SchemaLimits(max_events=2))

        nested: object = "leaf"
        for _ in range(20):
            nested = [nested]
        recursive = Capsule(
            schema_version="1",
            trace_id="trace",
            events=(Event("e", "unknown", None, 0, nested),),  # type: ignore[arg-type]
            metadata={},
        )
        with self.assertRaisesRegex(ValueError, "depth"):
            validate_capsule(recursive, limits=SchemaLimits(max_depth=8))

    def test_rejects_portable_workspace_path_aliases(self) -> None:
        base = Capsule(
            schema_version="1",
            trace_id="trace",
            events=(Event("run", "run", None, 0, {}),),
            metadata={},
        )
        aliases = (
            ("Predicate.py", "predicate.py"),
            ("\u00e9.py", "e\u0301.py"),
            ("name", "name. "),
        )
        for first, second in aliases:
            with (
                self.subTest(first=first, second=second),
                self.assertRaisesRegex(ValueError, "workspace path"),
            ):
                validate_capsule(
                    Capsule(
                        schema_version=base.schema_version,
                        trace_id=base.trace_id,
                        events=base.events,
                        metadata={},
                        workspace={
                            first: "raise SystemExit(1)\n",
                            second: "raise SystemExit(0)\n",
                        },
                    )
                )

    def test_rejects_windows_device_workspace_names_on_every_platform(self) -> None:
        capsule = Capsule(
            schema_version="1",
            trace_id="trace",
            events=(Event("run", "run", None, 0, {}),),
            metadata={},
            workspace={"CON.txt": "unsafe portable name"},
        )
        with self.assertRaisesRegex(ValueError, "workspace path"):
            validate_capsule(capsule)


if __name__ == "__main__":
    unittest.main()
