from __future__ import annotations

import pytest

from rmi.config import (
    DEFAULT_BUCKET_COUNT,
    DEFAULT_STAGE_MODELS,
    RMIConfig,
    RmiConfigError,
    load_rmi_config,
)
from rmi.model import RMIModel


def test_default_config_is_two_stage_linear():
    config = RMIConfig()

    assert config.stage_models == DEFAULT_STAGE_MODELS
    assert config.stage_count == 2
    assert config.bucket_count == DEFAULT_BUCKET_COUNT
    config.validate()


def test_load_config_from_environment():
    config = load_rmi_config(
        {"RMI_STAGE_MODELS": "constant,linear", "RMI_BUCKET_COUNT": "32"}
    )

    assert config.stage_models == ("constant", "linear")
    assert config.bucket_count == 32


def test_invalid_bucket_count_is_rejected():
    with pytest.raises(RmiConfigError, match="RMI_BUCKET_COUNT must be an integer"):
        load_rmi_config({"RMI_BUCKET_COUNT": "not-an-int"})

    with pytest.raises(RmiConfigError, match="bucket_count must be positive"):
        load_rmi_config({"RMI_BUCKET_COUNT": "0"})


def test_unknown_model_name_is_rejected():
    with pytest.raises(RmiConfigError, match="unknown RMI model name"):
        load_rmi_config({"RMI_STAGE_MODELS": "linear,quadratic"})

    with pytest.raises(RmiConfigError, match="at least one model"):
        load_rmi_config({"RMI_STAGE_MODELS": " , "})


def test_non_two_stage_config_fails_clearly_at_model_construction():
    with pytest.raises(RmiConfigError, match="exactly two stages"):
        RMIModel(RMIConfig(stage_models=("linear", "linear", "linear")))
