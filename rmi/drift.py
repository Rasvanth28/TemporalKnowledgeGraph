"""Update-drift experiment for the RMI lane.

Train on an initial key range, introduce new keys outside that range, measure
lookup accuracy/latency before retraining, retrain once, and measure again.
This is the synthetic answer to the design document's central open question.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import time

import numpy as np

from rmi.benchmark import benchmark_lookup
from rmi.config import RMIConfig, load_rmi_config
from rmi.fallback import binary_search_lookup
from rmi.keys import generate_queries, generate_sorted_keys
from rmi.train import retrain_rmi, train_rmi


@dataclass(frozen=True)
class DriftExperimentResult:
    initial_key_count: int
    new_key_count: int
    combined_key_count: int
    query_count: int
    distribution: str
    bucket_count: int
    stage_models: list[str]
    before_rmi_correct: int
    before_rmi_fallbacks: int
    before_rmi_median_ns: float
    after_rmi_correct: int
    after_rmi_fallbacks: int
    after_rmi_median_ns: float
    retrain_ns: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def run_drift_experiment(
    initial_key_count: int = 5_000,
    new_key_count: int = 500,
    query_count: int = 500,
    distribution: str = "uniform",
    config: RMIConfig | None = None,
    seed: int = 42,
    repeats: int = 3,
) -> DriftExperimentResult:
    """Run the before/after retraining drift experiment."""

    if new_key_count <= 0:
        raise ValueError("new_key_count must be positive")
    if query_count <= 0:
        raise ValueError("query_count must be positive")

    active_config = config or RMIConfig()
    initial_keys = generate_sorted_keys(initial_key_count, distribution=distribution, seed=seed)
    offset = int(initial_keys[-1]) + 1
    new_keys = generate_sorted_keys(new_key_count, distribution=distribution, seed=seed + 1) + offset
    combined_keys = np.unique(np.concatenate([initial_keys, new_keys])).astype(np.int64)

    queries = generate_queries(new_keys, query_count, seed=seed + 2)

    model_before = train_rmi(initial_keys, active_config)
    before = benchmark_lookup(
        model_before,
        queries,
        binary_search_lookup(initial_keys),
        repeats=repeats,
    )

    retrain_start = time.perf_counter_ns()
    model_after = retrain_rmi(combined_keys, active_config)
    retrain_ns = time.perf_counter_ns() - retrain_start

    after = benchmark_lookup(
        model_after,
        queries,
        binary_search_lookup(combined_keys),
        repeats=repeats,
    )

    return DriftExperimentResult(
        initial_key_count=len(initial_keys),
        new_key_count=len(new_keys),
        combined_key_count=len(combined_keys),
        query_count=len(queries),
        distribution=distribution,
        bucket_count=model_after.bucket_count,
        stage_models=list(active_config.stage_models),
        before_rmi_correct=before.rmi_correct,
        before_rmi_fallbacks=before.rmi_fallbacks,
        before_rmi_median_ns=before.rmi_median_ns,
        after_rmi_correct=after.rmi_correct,
        after_rmi_fallbacks=after.rmi_fallbacks,
        after_rmi_median_ns=after.rmi_median_ns,
        retrain_ns=retrain_ns,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic update-drift experiment.")
    parser.add_argument("--initial-keys", type=int, default=5_000)
    parser.add_argument("--new-keys", type=int, default=500)
    parser.add_argument("--queries", type=int, default=500)
    parser.add_argument("--distribution", choices=("uniform", "clustered"), default="uniform")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--bucket-count", type=int, default=None)
    parser.add_argument("--stage-models", default=None)
    args = parser.parse_args(argv)

    base_config = load_rmi_config()
    config = RMIConfig(
        stage_models=tuple(args.stage_models.split(",")) if args.stage_models else base_config.stage_models,
        bucket_count=args.bucket_count or base_config.bucket_count,
    )
    config.validate()

    result = run_drift_experiment(
        initial_key_count=args.initial_keys,
        new_key_count=args.new_keys,
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
