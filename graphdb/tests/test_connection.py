from __future__ import annotations

from typing import Any

from graphdb.config import Neo4jConfig
from graphdb.connection import Neo4jClient


class FakeRecord:
    def __init__(self, values: dict[str, Any]):
        self._values = values

    def data(self) -> dict[str, Any]:
        return dict(self._values)


class FakeSession:
    def __init__(self, database: str):
        self.database = database
        self.closed = False
        self.queries: list[tuple[str, dict[str, Any]]] = []
        self.write_work = None
        self.read_work = None

    def run(self, query: str, parameters: dict[str, Any]):
        self.queries.append((query, parameters))
        return [FakeRecord({"query": query, "parameters": parameters})]

    def execute_write(self, work):
        self.write_work = work
        return work("write-tx")

    def execute_read(self, work):
        self.read_work = work
        return work("read-tx")

    def close(self) -> None:
        self.closed = True


class FakeDriver:
    def __init__(self):
        self.verified = False
        self.closed = False
        self.databases: list[str] = []
        self.sessions: list[FakeSession] = []

    def verify_connectivity(self) -> None:
        self.verified = True

    def session(self, database: str) -> FakeSession:
        self.databases.append(database)
        session = FakeSession(database)
        self.sessions.append(session)
        return session

    def close(self) -> None:
        self.closed = True


def make_config() -> Neo4jConfig:
    return Neo4jConfig(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="secret-value",
        database="neo4j",
    )


def test_run_returns_plain_dicts_and_closes_session():
    driver = FakeDriver()
    client = Neo4jClient(make_config(), driver=driver)

    rows = client.run("RETURN $value AS value", {"value": 7})

    assert rows == [{"query": "RETURN $value AS value", "parameters": {"value": 7}}]
    assert driver.databases == ["neo4j"]
    assert driver.sessions[0].closed is True


def test_verify_connectivity_delegates():
    driver = FakeDriver()
    client = Neo4jClient(make_config(), driver=driver)

    client.verify_connectivity()

    assert driver.verified is True


def test_execute_write_and_read_delegate():
    driver = FakeDriver()
    client = Neo4jClient(make_config(), driver=driver)

    assert client.execute_write(lambda tx: f"write:{tx}") == "write:write-tx"
    assert client.execute_read(lambda tx: f"read:{tx}") == "read:read-tx"
    assert driver.sessions[0].closed is True
    assert driver.sessions[1].closed is True


def test_context_manager_closes_driver():
    driver = FakeDriver()
    with Neo4jClient(make_config(), driver=driver) as client:
        assert client.driver is driver
    assert driver.closed is True


class FakePlanResult:
    """EXPLAIN yields no records; the plan lives on the consumed summary."""

    def __init__(self, plan: dict[str, Any]):
        self.plan = plan

    def __iter__(self):
        return iter([])

    def consume(self):
        return self


class FakePlanSession(FakeSession):
    def run(self, query: str, parameters: dict[str, Any]):
        self.queries.append((query, parameters))
        return FakePlanResult({"operatorType": "NodeIndexSeekByRange", "arguments": {"Details": "event_date"}})


def test_explain_returns_plan_from_summary_not_records():
    driver = FakeDriver()
    driver.session = lambda database: driver.sessions.append(FakePlanSession(database)) or driver.sessions[-1]
    client = Neo4jClient(make_config(), driver=driver)

    assert client.run("EXPLAIN MATCH (e:Event) RETURN e") == []
    plan = client.explain("EXPLAIN MATCH (e:Event) RETURN e")

    assert plan["operatorType"] == "NodeIndexSeekByRange"
    assert all(session.closed for session in driver.sessions)
