from __future__ import annotations

import pytest

from rmi.config import RMIConfig
from rmi.drift import main, run_drift_experiment


def test_update_drift_recovers_all_queries_after_one_retrain():
    result = run_drift_experiment(
        initial_key_count=500,
        new_key_count=100,
        query_count=100,
        config=RMIConfig(bucket_count=16),
        seed=1,
        repeats=1,
    )

    assert result.before_rmi_correct == 0
    assert result.before_rmi_fallbacks == 100
    assert result.after_rmi_correct == 100
    assert result.after_rmi_fallbacks == 0
    assert result.combined_key_count == 600
    assert result.retrain_ns > 0


def test_update_drift_is_deterministic_in_correctness_counts():
    kwargs = dict(
        initial_key_count=300,
        new_key_count=50,
        query_count=50,
        config=RMIConfig(bucket_count=8),
        seed=2,
        repeats=1,
    )

    first = run_drift_experiment(**kwargs)
    second = run_drift_experiment(**kwargs)

    assert first.as_dict().keys() == second.as_dict().keys()
    assert first.before_rmi_correct == second.before_rmi_correct
    assert first.after_rmi_correct == second.after_rmi_correct
    assert first.before_rmi_fallbacks == second.before_rmi_fallbacks
    assert first.after_rmi_fallbacks == second.after_rmi_fallbacks


def test_update_drift_rejects_invalid_batch_sizes():
    with pytest.raises(ValueError, match="new_key_count must be positive"):
        run_drift_experiment(new_key_count=0)
    with pytest.raises(ValueError, match="query_count must be positive"):
        run_drift_experiment(query_count=0)


def test_update_drift_cli_runs(capsys):
    exit_code = main(
        [
            "--initial-keys",
            "128",
            "--new-keys",
            "16",
            "--queries",
            "16",
            "--repeats",
            "1",
            "--bucket-count",
            "8",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert '"before_rmi_correct": 0' in output
    assert '"after_rmi_correct": 16' in output
