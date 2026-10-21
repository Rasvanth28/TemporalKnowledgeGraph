"""Training and retraining entry points for the RMI lane.

``retrain_rmi`` is deliberately standalone and idempotent: the same keys and
configuration produce the same model. A real scheduler can call it later
without changing the training logic.
"""

from __future__ import annotations

import argparse
import json

import numpy as np

from rmi.config import RMIConfig, load_rmi_config
from rmi.keys import generate_sorted_keys
from rmi.model import RMIModel


def train_rmi(keys: np.ndarray, config: RMIConfig | None = None) -> RMIModel:
    """Fit a fresh two-stage RMI on sorted unique keys."""

    return RMIModel(config or load_rmi_config()).fit(keys)


def retrain_rmi(keys: np.ndarray, config: RMIConfig | None = None) -> RMIModel:
    """Idempotent retraining entry point.

    Calling this twice with the same keys and configuration produces an
    equivalent model. It is the function a future scheduler would trigger.
    """

    return train_rmi(keys, config)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train a two-stage RMI on synthetic keys.")
    parser.add_argument("--keys", type=int, default=10_000, help="Number of synthetic keys.")
    parser.add_argument(
        "--distribution",
        choices=("uniform", "clustered"),
        default="uniform",
        help="Synthetic key distribution.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    args = parser.parse_args(argv)

    keys = generate_sorted_keys(args.keys, distribution=args.distribution, seed=args.seed)
    model = train_rmi(keys)
    print(json.dumps(model.summary(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
