"""Shared pytest setup for every lane (graphdb, pipeline).

This lives at the repository root on purpose: ``pytest_collection_modifyitems`` sees
*all* collected tests no matter which conftest defines it, so per-lane copies of the
integration rules interfere with each other (a per-lane copy keyed on NEO4J_URI once silently
skipped every graphdb integration test in CI). Keep one copy, here.

Integration tests run only against a dedicated throwaway database configured by
NEO4J_TEST_* (see ``load_neo4j_test_config``) and are skipped when it is not
set. Each integration test starts from an empty database: the test database is
wiped before every test, so tests may assume nothing else is in the graph.
The real NEO4J_* database is never touched. The local .env is loaded for
developer convenience; its contents are never printed.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
import pytest

from graphdb.config import ConfigurationError, Neo4jConfig, load_neo4j_test_config

load_dotenv()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: requires a throwaway Neo4j instance configured by NEO4J_TEST_*",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if os.environ.get("NEO4J_TEST_URI"):
        return
    skip = pytest.mark.skip(reason="NEO4J_TEST_URI is not set; integration test skipped")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def neo4j_test_config() -> Neo4jConfig:
    try:
        return load_neo4j_test_config()
    except ConfigurationError as exc:
        pytest.fail(f"Refusing to run integration tests: {exc}", pytrace=False)


@pytest.fixture(scope="session")
def neo4j_test_schema(neo4j_test_config: Neo4jConfig) -> Neo4jConfig:
    # Indexes/constraints survive the per-test data wipe, so apply them once.
    from graphdb.apply_schema import apply_schema
    from graphdb.connection import Neo4jClient

    with Neo4jClient(neo4j_test_config) as client:
        report = apply_schema(client, wait_seconds=60)
    if not report.ok:
        pytest.fail(f"Test database schema incomplete: {report.missing}", pytrace=False)
    return neo4j_test_config


@pytest.fixture(autouse=True)
def _isolated_neo4j(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    if "integration" not in request.keywords:
        yield
        return

    config: Neo4jConfig = request.getfixturevalue("neo4j_test_schema")
    # Point every NEO4J_* reader (load_neo4j_config, CLIs, API) at the test database.
    monkeypatch.setenv("NEO4J_URI", config.uri)
    monkeypatch.setenv("NEO4J_USER", config.user)
    monkeypatch.setenv("NEO4J_PASSWORD", config.password)
    monkeypatch.setenv("NEO4J_DATABASE", config.database)

    from graphdb.connection import Neo4jClient

    with Neo4jClient(config) as client:
        client.run("MATCH (n) DETACH DELETE n")
    yield
