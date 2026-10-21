from __future__ import annotations

from graphdb.config import Neo4jConfig
from graphdb.health import check_health


def make_config() -> Neo4jConfig:
    return Neo4jConfig(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="super-secret-password",
        database="neo4j",
    )


class FakeHealthClient:
    def __init__(self, error: Exception | None = None, components_unsupported: bool = False):
        self.error = error
        self.components_unsupported = components_unsupported
        self.queries: list[str] = []

    def verify_connectivity(self) -> None:
        if self.error:
            raise self.error

    def run(self, query: str, parameters=None, database=None):
        self.queries.append(query)
        if "dbms.components" in query:
            if self.components_unsupported:
                raise RuntimeError("procedure not available")
            return [{"name": "Neo4j Kernel", "version": "5.26.32", "edition": "community"}]
        return [{"ok": 1}]


def test_health_reports_server_metadata():
    report = check_health(make_config(), FakeHealthClient())

    assert report.connected is True
    assert report.database == "neo4j"
    assert report.server_version == "5.26.32"
    assert report.edition == "community"


def test_health_falls_back_when_components_is_unavailable():
    client = FakeHealthClient(components_unsupported=True)

    report = check_health(make_config(), client)

    assert report.connected is True
    assert report.server_version is None
    assert any("RETURN 1" in query for query in client.queries)


def test_health_redacts_the_password_from_errors():
    report = check_health(
        make_config(),
        FakeHealthClient(error=RuntimeError("auth failed for super-secret-password")),
    )

    assert report.connected is False
    assert report.error is not None
    assert "super-secret-password" not in report.error
    assert "***" in report.error
