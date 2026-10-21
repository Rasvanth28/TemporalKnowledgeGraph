from __future__ import annotations

from rmi.config import RMIConfig
from rmi.keys import generate_sorted_keys
from rmi.train import retrain_rmi, train_rmi


def test_train_rmi_returns_fitted_model():
    keys = generate_sorted_keys(100, seed=1)
    model = train_rmi(keys, RMIConfig(bucket_count=8))

    assert model.summary()["key_count"] == 100
    assert all(model.lookup(int(key)).found for key in keys)


def test_retrain_rmi_is_idempotent_for_same_inputs():
    keys = generate_sorted_keys(100, seed=1)
    config = RMIConfig(bucket_count=8)

    first = retrain_rmi(keys, config).summary()
    second = retrain_rmi(keys, config).summary()

    assert first == second


def test_train_rmi_cli_runs(capsys):
    from rmi.train import main

    exit_code = main(["--keys", "64", "--distribution", "clustered", "--seed", "3"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert '"key_count": 64' in output
