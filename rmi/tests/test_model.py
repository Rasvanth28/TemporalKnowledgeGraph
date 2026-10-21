from __future__ import annotations

import numpy as np
import pytest

from rmi.config import RMIConfig, RmiConfigError
from rmi.keys import generate_sorted_keys
from rmi.model import RMIModel


def fitted_model(
    count: int = 500,
    distribution: str = "uniform",
    config: RMIConfig | None = None,
) -> tuple[RMIModel, np.ndarray]:
    keys = generate_sorted_keys(count, distribution=distribution, seed=11)
    return RMIModel(config or RMIConfig()).fit(keys), keys


@pytest.mark.parametrize("distribution", ["uniform", "clustered"])
def test_all_training_keys_are_found(distribution):
    model, keys = fitted_model(distribution=distribution)

    results = model.lookup_many(keys)

    assert all(result.found for result in results)
    assert all(result.index is not None for result in results)
    assert all(model.keys[result.index] == key for result, key in zip(results, keys))


def test_error_bound_windows_find_every_training_key_without_full_scan():
    model, keys = fitted_model(count=2000)

    results = model.lookup_many(keys)

    assert all(result.found for result in results)
    assert max(result.candidates_checked for result in results) < len(keys)


@pytest.mark.parametrize(
    "stage_models",
    [("linear", "linear"), ("constant", "constant"), ("linear", "constant")],
)
def test_config_driven_model_choices_stay_correct(stage_models):
    model, keys = fitted_model(config=RMIConfig(stage_models=stage_models))

    assert all(model.lookup(int(key)).found for key in keys)


def test_out_of_range_key_reports_fallback():
    model, keys = fitted_model()

    below = model.lookup(int(keys[0]) - 1)
    above = model.lookup(int(keys[-1]) + 1)

    assert below.found is False
    assert below.used_fallback is True
    assert below.reason == "out_of_range"
    assert above.reason == "out_of_range"


def test_in_range_unseen_key_reports_fallback_not_found():
    model, keys = fitted_model()
    unseen = int(keys[0]) + 1
    if unseen in set(int(value) for value in keys):
        unseen = int(keys[0]) + 2

    result = model.lookup(unseen)

    assert result.found is False
    assert result.used_fallback is True
    assert result.reason == "not_found"


def test_bucket_count_is_clamped_to_key_count():
    keys = generate_sorted_keys(3, seed=1)
    model = RMIModel(RMIConfig(bucket_count=999)).fit(keys)

    assert model.bucket_count == 3


def test_summary_reports_error_bounds():
    model, _ = fitted_model(count=100, config=RMIConfig(bucket_count=16))

    summary = model.summary()

    assert summary["key_count"] == 100
    assert summary["bucket_count"] == 16
    assert summary["stage_models"] == ["linear", "linear"]
    assert isinstance(summary["stage1_error_buckets"], int)
    assert isinstance(summary["max_stage2_error"], int)


def test_lookup_before_fit_raises():
    with pytest.raises(RuntimeError, match="fitted"):
        RMIModel().lookup(1)


def test_fit_rejects_unsorted_keys():
    with pytest.raises(ValueError, match="sorted"):
        RMIModel().fit(np.array([3, 1, 2]))


def test_fit_rejects_duplicate_keys():
    with pytest.raises(ValueError, match="unique"):
        RMIModel().fit(np.array([1, 1, 2]))


def test_fit_rejects_empty_input():
    with pytest.raises(ValueError, match="non-empty"):
        RMIModel().fit(np.array([], dtype=np.int64))


def test_three_stage_model_is_rejected_clearly():
    with pytest.raises(RmiConfigError, match="exactly two stages"):
        RMIModel(RMIConfig(stage_models=("linear", "linear", "linear")))
