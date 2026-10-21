from __future__ import annotations

import pytest

from graphdb.config import ConfigurationError, Neo4jConfig, load_neo4j_config


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
