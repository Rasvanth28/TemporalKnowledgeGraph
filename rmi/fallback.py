"""Fallback lookup contract for the RMI lane.

During C1–C3 the fallback is a binary search over the same sorted key array.
C4 injects a Neo4j-backed fallback built on Person B's stable query functions;
the benchmark harness does not change.
"""

from __future__ import annotations

from bisect import bisect_left
from typing import Callable

import numpy as np

FallbackLookup = Callable[[int], int | None]


def binary_search_lookup(keys: np.ndarray) -> FallbackLookup:
    """Return a correct fallback lookup over sorted unique keys."""

    values = [int(value) for value in np.asarray(keys, dtype=np.int64)]

    def lookup(key: int) -> int | None:
        query = int(key)
        index = bisect_left(values, query)
        if index < len(values) and values[index] == query:
            return index
        return None

    return lookup
