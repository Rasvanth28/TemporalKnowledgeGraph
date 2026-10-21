from __future__ import annotations

import pytest

from graphdb.config import ConfigurationError, Neo4jConfig, load_neo4j_config, load_neo4j_test_config


def test_load_config_from_injected_environment():
    config = load_neo4j_config(
        {
            "NEO4J_URI": "neo4j+s://example.databases.neo4j.io",
            "NEO4J_USER": "neo4j",
            "NEO4J_PASSWORD": "secret-value",
            "NEO4J_DATABASE": "neo4j",
        }
    )

    assert config.uri == "neo4j+s://example.databases.neo4j.io"
    assert config.user == "neo4j"
    assert config.password == "secret-value"
    assert config.database == "neo4j"


def test_default_database_is_neo4j():
    config = load_neo4j_config(
        {
            "NEO4J_URI": "bolt://localhost:7687",
            "NEO4J_USER": "neo4j",
            "NEO4J_PASSWORD": "secret-value",
        }
    )
    assert config.database == "neo4j"


def test_missing_variables_are_named_but_values_are_not_printed():
    with pytest.raises(ConfigurationError) as excinfo:
        load_neo4j_config({"NEO4J_URI": "bolt://localhost:7687"})

    message = str(excinfo.value)
    assert "NEO4J_USER" in message
    assert "NEO4J_PASSWORD" in message
    assert "bolt://localhost:7687" not in message


def test_invalid_uri_scheme_is_rejected():
    with pytest.raises(ConfigurationError, match="Invalid NEO4J_URI scheme"):
        load_neo4j_config(
            {
                "NEO4J_URI": "http://localhost:7474",
                "NEO4J_USER": "neo4j",
                "NEO4J_PASSWORD": "secret-value",
            }
        )


def test_password_is_hidden_from_config_repr():
    config = Neo4jConfig(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="super-secret-password",
        database="neo4j",
    )
    assert "super-secret-password" not in repr(config)


def test_password_is_preserved_without_trimming():
    config = load_neo4j_config(
        {
            "NEO4J_URI": "bolt://localhost:7687",
            "NEO4J_USER": "neo4j",
            "NEO4J_PASSWORD": "  spaced secret  ",
        }
    )
    assert config.password == "  spaced secret  "


def _test_env(**overrides: str) -> dict[str, str]:
    env = {
        "NEO4J_URI": "neo4j+s://real.databases.neo4j.io",
        "NEO4J_TEST_URI": "bolt://localhost:7688",
        "NEO4J_TEST_USER": "neo4j",
        "NEO4J_TEST_PASSWORD": "test-secret",
    }
    env.update(overrides)
    return env


def test_test_config_reads_only_test_variables():
    config = load_neo4j_test_config(_test_env())

    assert config.uri == "bolt://localhost:7688"
    assert config.password == "test-secret"
    assert config.database == "neo4j"


def test_test_config_refuses_the_real_database():
    with pytest.raises(ConfigurationError, match="must not point"):
        load_neo4j_test_config(_test_env(NEO4J_URI="bolt://localhost:7688/"))


def test_test_config_refuses_remote_hosts_unless_allowed():
    remote = "neo4j+s://other.databases.neo4j.io"
    with pytest.raises(ConfigurationError, match="not local"):
        load_neo4j_test_config(_test_env(NEO4J_TEST_URI=remote))

    config = load_neo4j_test_config(_test_env(NEO4J_TEST_URI=remote, NEO4J_TEST_ALLOW_REMOTE="true"))
    assert config.uri == remote


def test_test_config_missing_variables_never_echo_values():
    with pytest.raises(ConfigurationError) as exc:
        load_neo4j_test_config({"NEO4J_TEST_URI": "bolt://localhost:7688", "NEO4J_TEST_PASSWORD": "hunter2"})
    assert "hunter2" not in str(exc.value)
