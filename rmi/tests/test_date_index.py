from bisect import bisect_left

import numpy as np
import pytest

from rmi.config import RMIConfig
from rmi.date_index import DateIndex
from rmi.keys import generate_sorted_keys
from rmi.train import train_rmi


def skewed_days(seed: int = 3) -> np.ndarray:
    """Shaped like the live graph: a sparse tail over two centuries, then a dense recent month."""

    rng = np.random.default_rng(seed)
    tail = rng.integers(-61_000, 20_000, size=300)
    recent = np.arange(20_720, 20_753)
    return np.unique(np.concatenate([tail, recent]))


@pytest.mark.parametrize("keys", [skewed_days(), generate_sorted_keys(500, "clustered"), np.array([5])])
@pytest.mark.parametrize("config", [RMIConfig(), RMIConfig(bucket_count=4), RMIConfig(("linear", "constant"), 16)])
def test_lower_bound_matches_bisect_without_fallback_for_keys_in_and_around_the_range(keys, config):
    model = train_rmi(keys, config)
    values = keys.tolist()
    for key in range(int(keys[0]) - 2, int(keys[-1]) + 3, max(1, (int(keys[-1]) - int(keys[0])) // 5000)):
        result = model.lower_bound(key)
        assert not result.used_fallback and result.index == bisect_left(values, key), key
    for key in values:
        assert model.lower_bound(key).index == bisect_left(values, key)
        assert model.lookup(key).index == bisect_left(values, key)


def test_lookup_routes_to_one_bucket_even_when_stage_one_is_far_off():
    model = train_rmi(skewed_days(), RMIConfig(bucket_count=128))
    assert model.stage1_error_buckets > 5  # the long tail throws stage 1 off
    assert max(model.lookup(int(k)).candidates_checked for k in skewed_days()) <= 2 * int(model.stage2_errors.max()) + 1


ROWS = [(10, "b"), (10, "a"), (12, "c"), (15, "d"), (15, "e"), (15, "f"), (30, "g")]


def test_date_index_answers_days_and_ranges_like_a_sorted_scan():
    index = DateIndex.build(ROWS, RMIConfig(bucket_count=2))
    assert index.on(10) == ["a", "b"]
    assert index.on(11) == []
    assert index.between(11, 15) == ["c", "d", "e", "f"]
    assert index.between(0, 100) == ["a", "b", "c", "d", "e", "f", "g"]
    assert index.between(31, 40) == [] and index.between(0, 9) == []
    assert index.between(15, 12) == []
    assert index.summary()["events"] == 7 and index.summary()["days"] == 4


def test_date_index_uses_the_injected_fallback_when_the_model_cannot_answer():
    calls = []

    def fallback(days):
        def lower(key):
            calls.append(key)
            return bisect_left(days.tolist(), key)
        return lower

    index = DateIndex.build(ROWS, fallback=fallback)
    index.model.lower_bound = lambda key: type("R", (), {"used_fallback": True})()
    assert index.between(11, 15) == ["c", "d", "e", "f"]
    assert calls == [11, 16] and index.fallbacks == 2


def test_date_index_rejects_an_empty_event_set():
    with pytest.raises(ValueError):
        DateIndex.build([])
