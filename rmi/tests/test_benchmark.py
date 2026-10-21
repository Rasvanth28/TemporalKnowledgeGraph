from __future__ import annotations

import numpy as np
import pytest

from rmi.benchmark import benchmark_lookup, main, run_synthetic_benchmark
from rmi.config import RMIConfig
from rmi.fallback import binary_search_lookup
from rmi.keys import generate_queries, generate_sorted_keys
from rmi.train import train_rmi


def test_binary_search_fallback_finds_existing_and_missing_keys():
    keys = generate_sorted_keys(100, seed=1)
    lookup = binary_search_lookup(keys)

    found = lookup(int(keys[37]))
    missing = lookup(int(keys[-1]) + 1)

    assert found == 37
    assert missing is None


def test_benchmark_rmi_and_fallback_are_both_correct_on_the_same_queries():
    keys = generate_sorted_keys(300, seed=2)
    model = train_rmi(keys, RMIConfig(bucket_count=16))
    queries = generate_queries(keys, 50, seed=3)

    result = benchmark_lookup(model, queries, binary_search_lookup(keys), repeats=1)

    assert result.rmi_correct == 50
    assert result.rmi_fallbacks == 0
    assert result.fallback_correct == 50
    assert result.rmi_median_ns >= 0
    assert result.fallback_median_ns >= 0


def test_benchmark_reports_fallback_misses_from_an_unreliable_fallback():
    keys = generate_sorted_keys(50, seed=4)
    model = train_rmi(keys, RMIConfig(bucket_count=8))
    queries = generate_queries(keys, 10, seed=5)

    result = benchmark_lookup(model, queries, lambda _key: None, repeats=1)

    assert result.rmi_correct == 10
    assert result.fallback_correct == 0


def test_benchmark_rejects_non_positive_repeats():
    keys = generate_sorted_keys(20, seed=1)
    model = train_rmi(keys)
    with pytest.raises(ValueError, match="repeats must be a positive integer"):
        benchmark_lookup(model, keys[:1], binary_search_lookup(keys), repeats=0)


def test_run_synthetic_benchmark_is_self_contained():
    result = run_synthetic_benchmark(
        key_count=200,
        query_count=40,
        distribution="clustered",
        config=RMIConfig(bucket_count=8),
        seed=6,
        repeats=1,
    )

    assert result.key_count == 200
    assert result.query_count == 40
    assert result.rmi_correct == 40
    assert result.fallback_correct == 40
    assert result.stage_models == ["linear", "linear"]


def test_benchmark_cli_runs(capsys):
    exit_code = main(["--keys", "128", "--queries", "32", "--repeats", "1", "--bucket-count", "8"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert '"key_count": 128' in output
    assert '"rmi_correct": 32' in output
