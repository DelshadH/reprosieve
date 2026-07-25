from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar

T = TypeVar("T")


class PredicateResult(Enum):
    REPRODUCES = "reproduces"
    ABSENT = "absent"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class ReductionResult(Generic[T]):
    items: tuple[T, ...]
    predicate_calls: int


def _partition_ranges(length: int, parts: int) -> list[tuple[int, int]]:
    size, remainder = divmod(length, parts)
    ranges: list[tuple[int, int]] = []
    start = 0
    for index in range(parts):
        width = size + (1 if index < remainder else 0)
        if width:
            ranges.append((start, start + width))
        start += width
    return ranges


def ddmin(
    items: Sequence[T],
    predicate: Callable[[tuple[T, ...]], PredicateResult],
) -> ReductionResult[T]:
    """Return a 1-minimal reproducing subsequence under deletion.

    INVALID is never treated as ABSENT and never accepted. The caller owns
    dependency repair/validation before invoking the predicate.
    """
    current = tuple(items)
    calls = 1
    if predicate(current) is not PredicateResult.REPRODUCES:
        raise ValueError("initial candidate does not reproduce the target failure")

    granularity = 2
    while len(current) >= 2:
        ranges = _partition_ranges(len(current), min(granularity, len(current)))
        reduced = False
        for start, end in ranges:
            candidate = current[:start] + current[end:]
            calls += 1
            if predicate(candidate) is PredicateResult.REPRODUCES:
                current = candidate
                granularity = max(2, granularity - 1)
                reduced = True
                break
        if reduced:
            continue
        if granularity >= len(current):
            break
        granularity = min(len(current), granularity * 2)

    # Independent linear pass makes the returned sequence 1-minimal even when
    # partition boundaries or invalid candidates prevented an earlier deletion.
    index = 0
    while index < len(current):
        candidate = current[:index] + current[index + 1 :]
        calls += 1
        if predicate(candidate) is PredicateResult.REPRODUCES:
            current = candidate
        else:
            index += 1

    return ReductionResult(items=current, predicate_calls=calls)
