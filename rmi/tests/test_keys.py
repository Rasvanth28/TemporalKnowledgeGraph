from __future__ import annotations

import numpy as np
import pytest

from rmi.keys import generate_queries, generate_sorted_keys


@pytest.mark.parametrize("distribution", ["uniform", "clustered"])
def test_generated_keys_are_sorted_unique_and_correct_length(distribution):
    keys = generate_sorted_keys(200, distribution=distribution, seed=3)

    assert len(keys) == 200
    assert len(np.unique(keys)) == 200
    assert np.all(keys[1:] >= keys[:-1])


def test_generation_is_deterministic_for_a_seed():
    assert np.array_equal(
        generate_sorted_keys(50, seed=5), generate_sorted_keys(50, seed=5)
    )
    assert not np.array_equal(
        generate_sorted_keys(50, seed=5), generate_sorted_keys(50, seed=6)
    )


def test_invalid_key_requests_are_rejected():
    with pytest.raises(ValueError, match="count must be a positive integer"):
        generate_sorted_keys(0)
    with pytest.raises(ValueError, match="distribution must be"):
        generate_sorted_keys(10, distribution="zipf")


def test_generate_queries_samples_existing_keys():
    keys = generate_sorted_keys(100, seed=1)
    queries = generate_queries(keys, 25, seed=2)

    assert len(queries) == 25
    assert set(int(value) for value in queries) <= set(int(value) for value in keys)


def test_generate_queries_rejects_invalid_input():
    with pytest.raises(ValueError, match="count must be a positive integer"):
        generate_queries(np.array([1, 2, 3]), 0)
    with pytest.raises(ValueError, match="non-empty 1-D array"):
        generate_queries(np.array([]), 1)
