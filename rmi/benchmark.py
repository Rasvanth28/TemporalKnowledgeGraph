"""Benchmark the RMI against an injected fallback on the same query set.

The independent benchmark substitutes a binary-search fallback for Neo4j. The
harness is deliberately fallback-agnostic so C4 can inject a Neo4j-backed
lookup without changing the measurement logic.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import statistics
import time

import numpy as np

from rmi.config import RMIConfig, load_rmi_config
from rmi.fallback import FallbackLookup, binary_search_lookup
from rmi.keys import generate_queries, generate_sorted_keys
from rmi.model import RMIModel
from rmi.train import train_rmi


@dataclass(frozen=True)
class BenchmarkResult:
    key_count: int
    query_count: int
    bucket_count: int
    stage_models: list[str]
    rmi_correct: int
    rmi_fallbacks: int
    fallback_correct: int
    rmi_mean_ns: float
    rmi_median_ns: float
    rmi_p95_ns: float
    fallback_mean_ns: float
    fallback_median_ns: float
    fallback_p95_ns: float
    speedup: float

    def as_dict(self) -> dict[str, object]:
        return {
            "key_count": self.key_count,
            "query_count": self.query_count,
            "bucket_count": self.bucket_count,
            "stage_models": self.stage_models,
            "rmi_correct": self.rmi_correct,
            "rmi_fallbacks": self.rmi_fallbacks,
            "fallback_correct": self.fallback_correct,
            "rmi_mean_ns": self.rmi_mean_ns,
            "rmi_median_ns": self.rmi_median_ns,
            "rmi_p95_ns": self.rmi_p95_ns,
            "fallback_mean_ns": self.fallback_mean_ns,
            "fallback_median_ns": self.fallback_median_ns,
            "fallback_p95_ns": self.fallback_p95_ns,
            "speedup": self.speedup,
        }


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
    return float(ordered[index])


def _time_call(function, query: int, repeats: int) -> float:
    samples: list[int] = []
    for _ in range(repeats):
        start = time.perf_counter_ns()
        function(query)
        samples.append(time.perf_counter_ns() - start)
    return float(statistics.median(samples))


def benchmark_lookup(
    model: RMIModel,
    queries: np.ndarray,
    fallback: FallbackLookup,
    repeats: int = 3,
) -> BenchmarkResult:
    """Benchmark RMI and fallback on identical query keys."""

    if repeats <= 0:
        raise ValueError("repeats must be a positive integer")
    keys = model.keys
    query_values = [int(value) for value in np.asarray(queries, dtype=np.int64)]

    rmi_correct = 0
    rmi_fallbacks = 0
    rmi_times: list[float] = []
    for query in query_values:
        result = model.lookup(query)
        if result.found and result.index is not None and int(keys[result.index]) == query:
            rmi_correct += 1
        if result.used_fallback:
            rmi_fallbacks += 1
        rmi_times.append(_time_call(lambda value: model.lookup(value), query, repeats))

    fallback_correct = 0
    fallback_times: list[float] = []
    for query in query_values:
        index = fallback(query)
        if index is not None and int(keys[index]) == query:
            fallback_correct += 1
        fallback_times.append(_time_call(fallback, query, repeats))

    rmi_median = float(statistics.median(rmi_times)) if rmi_times else 0.0
    fallback_median = float(statistics.median(fallback_times)) if fallback_times else 0.0
    speedup = (fallback_median / rmi_median) if rmi_median > 0 else 0.0

    return BenchmarkResult(
        key_count=len(keys),
        query_count=len(query_values),
        bucket_count=model.bucket_count,
        stage_models=list(model.config.stage_models),
        rmi_correct=rmi_correct,
        rmi_fallbacks=rmi_fallbacks,
        fallback_correct=fallback_correct,
        rmi_mean_ns=float(statistics.mean(rmi_times)) if rmi_times else 0.0,
        rmi_median_ns=rmi_median,
        rmi_p95_ns=_p95(rmi_times),
        fallback_mean_ns=float(statistics.mean(fallback_times)) if fallback_times else 0.0,
        fallback_median_ns=fallback_median,
        fallback_p95_ns=_p95(fallback_times),
        speedup=speedup,
    )


def run_synthetic_benchmark(
    key_count: int = 10_000,
    query_count: int = 2_000,
    distribution: str = "uniform",
    config: RMIConfig | None = None,
    seed: int = 42,
    repeats: int = 3,
    fallback: FallbackLookup | None = None,
) -> BenchmarkResult:
    """Train on synthetic keys and benchmark both paths on the same queries."""

    keys = generate_sorted_keys(key_count, distribution=distribution, seed=seed)
    model = train_rmi(keys, config or RMIConfig())
    queries = generate_queries(keys, query_count, seed=seed + 1)
    active_fallback = fallback or binary_search_lookup(keys)
    return benchmark_lookup(model, queries, active_fallback, repeats=repeats)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic RMI-vs-fallback benchmark.")
    parser.add_argument("--keys", type=int, default=10_000)
    parser.add_argument("--queries", type=int, default=2_000)
    parser.add_argument("--distribution", choices=("uniform", "clustered"), default="uniform")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--bucket-count", type=int, default=None)
    parser.add_argument("--stage-models", default=None, help="Comma-separated model names.")
    args = parser.parse_args(argv)

    base_config = load_rmi_config()
    config = RMIConfig(
        stage_models=tuple(args.stage_models.split(",")) if args.stage_models else base_config.stage_models,
        bucket_count=args.bucket_count or base_config.bucket_count,
    )
    config.validate()

    result = run_synthetic_benchmark(
        key_count=args.keys,
        query_count=args.queries,
        distribution=args.distribution,
        config=config,
        seed=args.seed,
        repeats=args.repeats,
    )
    print(json.dumps(result.as_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
