from __future__ import annotations

import unittest

from reprosieve.ddmin import PredicateResult, ddmin


class DdminTests(unittest.TestCase):
    def test_finds_one_minimal_pair(self) -> None:
        required = {"tool-call", "bad-result"}

        def predicate(candidate: tuple[str, ...]) -> PredicateResult:
            return (
                PredicateResult.REPRODUCES
                if required.issubset(candidate)
                else PredicateResult.ABSENT
            )

        source = tuple(f"noise-{index}" for index in range(20)) + tuple(required)
        result = ddmin(source, predicate)
        self.assertEqual(set(result.items), required)
        for index in range(len(result.items)):
            candidate = result.items[:index] + result.items[index + 1 :]
            self.assertIsNot(predicate(candidate), PredicateResult.REPRODUCES)

    def test_preserves_duplicate_positions_correctly(self) -> None:
        def predicate(candidate: tuple[str, ...]) -> PredicateResult:
            return PredicateResult.REPRODUCES if candidate.count("needed") >= 2 else PredicateResult.ABSENT

        result = ddmin(("noise", "needed", "noise", "needed", "noise"), predicate)
        self.assertEqual(result.items, ("needed", "needed"))

    def test_invalid_is_not_accepted(self) -> None:
        def predicate(candidate: tuple[int, ...]) -> PredicateResult:
            if 3 not in candidate:
                return PredicateResult.INVALID
            return PredicateResult.REPRODUCES if 7 in candidate else PredicateResult.ABSENT

        result = ddmin((1, 2, 3, 4, 7, 8), predicate)
        self.assertIn(3, result.items)
        self.assertIn(7, result.items)


if __name__ == "__main__":
    unittest.main()
