"""Configuration for the RMI lane.

Stage count and per-stage model types are configuration, not hardcoded call
sites. The current implementation supports a two-stage RMI; a different stage
count fails with a clear error instead of silently misbehaving.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os

DEFAULT_STAGE_MODELS = ("linear", "linear")
DEFAULT_BUCKET_COUNT = 128
VALID_MODEL_NAMES = ("linear", "constant")


class RmiConfigError(ValueError):
    """Raised when RMI configuration is invalid or unsupported."""


@dataclass(frozen=True)
class RMIConfig:
    stage_models: tuple[str, ...] = DEFAULT_STAGE_MODELS
    bucket_count: int = DEFAULT_BUCKET_COUNT

    @property
    def stage_count(self) -> int:
        return len(self.stage_models)

    def validate(self) -> None:
        if not self.stage_models:
            raise RmiConfigError("stage_models must contain at least one model name")
        unknown = [name for name in self.stage_models if name not in VALID_MODEL_NAMES]
        if unknown:
            raise RmiConfigError(
                f"unknown RMI model name(s): {', '.join(unknown)}; "
                f"valid names are: {', '.join(VALID_MODEL_NAMES)}"
            )
        if not isinstance(self.bucket_count, int) or isinstance(self.bucket_count, bool):
            raise RmiConfigError("bucket_count must be an integer")
        if self.bucket_count <= 0:
            raise RmiConfigError("bucket_count must be positive")


def _parse_stage_models(value: str) -> tuple[str, ...]:
    names = tuple(part.strip() for part in value.split(",") if part.strip())
    if not names:
        raise RmiConfigError("RMI_STAGE_MODELS must name at least one model")
    return names


def load_rmi_config(env: Mapping[str, str] | None = None) -> RMIConfig:
    """Load RMI configuration from ``RMI_*`` environment variables.

    No shared ``.env.example`` edit is made by this lane while Person B's
    PRs are open; the variables are documented in the contribution README.
    """

    env = os.environ if env is None else env
    stage_models = _parse_stage_models(env.get("RMI_STAGE_MODELS", ",".join(DEFAULT_STAGE_MODELS)))

    raw_bucket_count = env.get("RMI_BUCKET_COUNT", str(DEFAULT_BUCKET_COUNT))
    try:
        bucket_count = int(raw_bucket_count)
    except ValueError as exc:
        raise RmiConfigError("RMI_BUCKET_COUNT must be an integer") from exc

    config = RMIConfig(stage_models=stage_models, bucket_count=bucket_count)
    config.validate()
    return config
