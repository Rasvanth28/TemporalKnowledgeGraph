"""Synthetic sorted-key generators for the independent RMI experiments.

Person C can train and benchmark before Person B's graph export exists. The
generators produce strict integer sorted, unique keys.
"""

from __future__ import annotations

import numpy as np


def _unique_sorted(values: np.ndarray) -> np.ndarray:
    values = np.unique(values.astype(np.int64))
    return np.sort(values)


def generate_sorted_keys(
    count: int,
    distribution: str = "uniform",
    seed: int = 42,
) -> np.ndarray:
    """Generate ``count`` sorted, unique integer keys.

    Supported distributions: ``uniform`` and ``clustered``.
    """

    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        raise ValueError("count must be a positive integer")
    if distribution not in {"uniform", "clustered"}:
        raise ValueError("distribution must be 'uniform' or 'clustered'")

    rng = np.random.default_rng(seed)

    if distribution == "uniform":
        # Oversample and unique until the requested count is available.
        high = max(count * 10, 1000)
        values = rng.integers(0, high, size=count * 3, dtype=np.int64)
        keys = _unique_sorted(values)
        if len(keys) < count:
            keys = np.arange(count, dtype=np.int64)
        return keys[:count]

    cluster_count = max(2, count // 250)
    centers = rng.integers(0, max(count * 20, 2000), size=cluster_count, dtype=np.int64)
    values: list[np.ndarray] = []
    for center in centers:
        size = int(rng.integers(max(1, count // (cluster_count * 2)), max(2, count // cluster_count) + 1))
        spread = max(1, int(rng.integers(5, 500)))
        values.append(rng.integers(center - spread, center + spread + 1, size=size, dtype=np.int64))
    keys = _unique_sorted(np.concatenate(values)) if values else np.arange(count, dtype=np.int64)
    if len(keys) < count:
        keys = np.concatenate([keys, np.arange(keys[-1] + 1, keys[-1] + 1 + (count - len(keys)), dtype=np.int64)])
    return keys[:count]


def generate_queries(keys: np.ndarray, count: int, seed: int = 7) -> np.ndarray:
    """Sample ``count`` query keys from an existing key array."""

    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        raise ValueError("count must be a positive integer")
    keys = np.asarray(keys, dtype=np.int64)
    if keys.ndim != 1 or len(keys) == 0:
        raise ValueError("keys must be a non-empty 1-D array")
    rng = np.random.default_rng(seed)
    return rng.choice(keys, size=count, replace=True)
