"""A small two-stage Recursive Model Index with error-bound lookup.

Stage 1 predicts a normalized position and therefore a bucket. Stage 2 models
predict local positions inside their bucket. Each stage's maximum training
error sizes a bounded correction window, so every training key is guaranteed to
be found without a full scan. Out-of-range or unmatched keys report a fallback
reason for the Neo4j path added in the integration PR.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from rmi.config import RMIConfig, RmiConfigError


class NumericModel(Protocol):
    def fit(self, x: np.ndarray, y: np.ndarray) -> None: ...
    def predict(self, x: np.ndarray) -> np.ndarray: ...
    def predict_scalar(self, value: float) -> float: ...
    def max_abs_error(self, x: np.ndarray, y: np.ndarray) -> float: ...


class LinearModel:
    """Least-squares linear model, safe for one-point buckets."""

    slope_: float
    intercept_: float

    def fit(self, x: np.ndarray, y: np.ndarray) -> None:
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        if len(x) < 2:
            self.slope_ = 0.0
            self.intercept_ = float(y[0]) if len(y) else 0.0
            return
        self.slope_, self.intercept_ = np.polyfit(x, y, 1)

    def predict(self, x: np.ndarray) -> np.ndarray:
        return self.slope_ * np.asarray(x, dtype=float) + self.intercept_

    def predict_scalar(self, value: float) -> float:
        return self.slope_ * float(value) + self.intercept_

    def max_abs_error(self, x: np.ndarray, y: np.ndarray) -> float:
        if len(x) == 0:
            return 0.0
        return float(np.max(np.abs(self.predict(x) - np.asarray(y, dtype=float))))


class ConstantModel:
    """Mean predictor, useful for config-driven model comparisons."""

    value_: float

    def fit(self, x: np.ndarray, y: np.ndarray) -> None:
        self.value_ = float(np.mean(y)) if len(y) else 0.0

    def predict(self, x: np.ndarray) -> np.ndarray:
        x = np.asarray(x)
        return np.full(x.shape, self.value_, dtype=float)

    def predict_scalar(self, value: float) -> float:
        return self.value_

    def max_abs_error(self, x: np.ndarray, y: np.ndarray) -> float:
        if len(x) == 0:
            return 0.0
        return float(np.max(np.abs(self.predict(x) - np.asarray(y, dtype=float))))


def make_model(name: str) -> NumericModel:
    if name == "linear":
        return LinearModel()
    if name == "constant":
        return ConstantModel()
    raise RmiConfigError(f"unknown RMI model name: {name!r}")


@dataclass(frozen=True)
class LookupResult:
    found: bool
    index: int | None
    candidates_checked: int
    used_fallback: bool
    reason: str | None = None


class RMIModel:
    """Two-stage RMI over sorted, unique integer keys."""

    def __init__(self, config: RMIConfig | None = None):
        self.config = config or RMIConfig()
        self.config.validate()
        if self.config.stage_count != 2:
            raise RmiConfigError(
                "this MVP implements exactly two stages; "
                f"got {self.config.stage_count} stage_models"
            )
        self._fitted = False

    def fit(self, keys: np.ndarray) -> "RMIModel":
        keys = np.asarray(keys, dtype=np.int64)
        if keys.ndim != 1 or len(keys) == 0:
            raise ValueError("keys must be a non-empty 1-D array")
        if np.any(keys[1:] < keys[:-1]):
            raise ValueError("keys must be sorted in ascending order")
        if len(np.unique(keys)) != len(keys):
            raise ValueError("keys must be unique")

        self.keys = keys
        self.n = len(keys)
        self.min_key = int(keys[0])
        self.max_key = int(keys[-1])
        self.positions = np.arange(self.n, dtype=np.int64)

        self.bucket_count = min(self.config.bucket_count, self.n)
        self.bucket_count = max(1, self.bucket_count)
        boundaries = np.floor(np.linspace(0, self.n, self.bucket_count + 1)).astype(np.int64)
        self.bucket_starts = boundaries[:-1]
        self.bucket_ends = boundaries[1:]

        # Stage 1: keys -> normalized position [0, 1].
        y_stage1 = self.positions.astype(float) / max(self.n - 1, 1)
        self.stage1 = make_model(self.config.stage_models[0])
        self.stage1.fit(keys, y_stage1)

        predicted_norm = np.clip(self.stage1.predict(keys), 0.0, 1.0)
        predicted_bucket = np.clip(
            (predicted_norm * self.bucket_count).astype(np.int64),
            0,
            self.bucket_count - 1,
        )
        true_bucket = np.clip(
            np.searchsorted(self.bucket_starts, self.positions, side="right") - 1,
            0,
            self.bucket_count - 1,
        )
        self.stage1_error_buckets = int(np.max(np.abs(predicted_bucket - true_bucket)))

        # Stage 2: one local-position model per bucket.
        self.stage2_models: list[NumericModel] = []
        self.stage2_errors = np.zeros(self.bucket_count, dtype=np.int64)
        for bucket in range(self.bucket_count):
            start, end = int(self.bucket_starts[bucket]), int(self.bucket_ends[bucket])
            x_bucket = keys[start:end]
            y_bucket = self.positions[start:end] - start
            model = make_model(self.config.stage_models[1])
            model.fit(x_bucket, y_bucket)
            self.stage2_models.append(model)
            self.stage2_errors[bucket] = int(np.ceil(model.max_abs_error(x_bucket, y_bucket)))

        self._fitted = True
        return self

    def _require_fitted(self) -> None:
        if not self._fitted:
            raise RuntimeError("RMIModel must be fitted before lookup")

    def _route(self, key: int) -> int:
        """Stage 1, corrected: the bucket whose key range holds ``key``.

        The prediction is off by at most ``stage1_error_buckets``; comparing the
        key with bucket boundaries walks to the right bucket in that many steps,
        so only one stage-2 model runs.
        """

        predicted_norm = min(max(self.stage1.predict_scalar(key), 0.0), 1.0)
        bucket = int(min(max(int(predicted_norm * self.bucket_count), 0), self.bucket_count - 1))
        while bucket > 0 and key < int(self.keys[self.bucket_starts[bucket]]):
            bucket -= 1
        while bucket < self.bucket_count - 1 and key >= int(self.keys[self.bucket_starts[bucket + 1]]):
            bucket += 1
        return bucket

    def _window(self, bucket: int, key: int, slack: int = 0) -> tuple[int, int]:
        """Stage 2: inclusive positions in ``bucket`` that must hold ``key`` if present."""

        start = int(self.bucket_starts[bucket])
        end = int(self.bucket_ends[bucket])
        global_prediction = int(round(start + self.stage2_models[bucket].predict_scalar(key)))
        window = int(self.stage2_errors[bucket]) + slack
        return max(start, global_prediction - window), min(end - 1, global_prediction + window)

    def lookup(self, key: int) -> LookupResult:
        self._require_fitted()
        key = int(key)

        if key < self.min_key or key > self.max_key:
            return LookupResult(
                found=False,
                index=None,
                candidates_checked=0,
                used_fallback=True,
                reason="out_of_range",
            )

        checked = 0
        search_start, search_end = self._window(self._route(key), key)
        for position in range(search_start, search_end + 1):
            checked += 1
            if int(self.keys[position]) == key:
                return LookupResult(
                    found=True,
                    index=position,
                    candidates_checked=checked,
                    used_fallback=False,
                    reason=None,
                )

        return LookupResult(
            found=False,
            index=None,
            candidates_checked=checked,
            used_fallback=True,
            reason="not_found",
        )

    def lower_bound(self, key: int) -> LookupResult:
        """Position of the first key >= ``key`` (``n`` when every key is smaller).

        Range queries start and end on keys the model never saw (days without
        events). Both stage models are non-decreasing, so an unseen key between
        training keys k_i < key < k_i+1 is predicted between their predictions and
        lands at most one position further from its answer (i + 1) than the
        training error: the window is widened by one. Each candidate is still
        verified against its left neighbour, and a miss reports ``used_fallback``.
        """

        self._require_fitted()
        key = int(key)
        if key <= self.min_key:
            return LookupResult(found=True, index=0, candidates_checked=0, used_fallback=False)
        if key > self.max_key:
            return LookupResult(found=True, index=self.n, candidates_checked=0, used_fallback=False)

        bucket = self._route(key)
        end = int(self.bucket_ends[bucket])
        if key > int(self.keys[end - 1]):  # in the gap before the next bucket
            return LookupResult(found=True, index=end, candidates_checked=1, used_fallback=False)
        checked = 0
        search_start, search_end = self._window(bucket, key, slack=1)
        for position in range(search_start, search_end + 1):
            checked += 1
            if int(self.keys[position]) >= key and int(self.keys[position - 1]) < key:
                return LookupResult(
                    found=True,
                    index=position,
                    candidates_checked=checked,
                    used_fallback=False,
                )

        return LookupResult(
            found=False,
            index=None,
            candidates_checked=checked,
            used_fallback=True,
            reason="boundary_outside_window",
        )

    def lookup_many(self, keys: np.ndarray) -> list[LookupResult]:
        return [self.lookup(int(key)) for key in np.asarray(keys)]

    def summary(self) -> dict[str, object]:
        self._require_fitted()
        return {
            "key_count": self.n,
            "bucket_count": self.bucket_count,
            "stage_models": list(self.config.stage_models),
            "stage1_error_buckets": self.stage1_error_buckets,
            "max_stage2_error": int(np.max(self.stage2_errors)) if self.bucket_count else 0,
            "mean_stage2_error": float(np.mean(self.stage2_errors)) if self.bucket_count else 0.0,
            "min_key": self.min_key,
            "max_key": self.max_key,
        }
