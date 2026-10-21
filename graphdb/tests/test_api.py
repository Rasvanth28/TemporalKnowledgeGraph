from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from fastapi.testclient import TestClient

from graphdb.api import create_app
from graphdb.config import Neo4jConfig
from graphdb.tests.test_queries_unit import FakeQueryClient, event_row

TEST_CONFIG = Neo4jConfig(
    uri="bolt://test.invalid:7687",
    user="test",
    password="",
    database="neo4j",
)


class FakeApiClient(FakeQueryClient):
    def verify_connectivity(self) -> None:
        pass

    def close(self) -> None:
        pass


def responses() -> dict[str, Any]:
    return {
        "CALL dbms.components": [
            {"name": "Neo4j Kernel", "version": "5.26.32", "edition": "community"}
        ],
        "MATCH (n:Entity {name: $name})": [
            {"id": "test_unit_ent", "name": "Unit Entity", "type": "ORG"}
        ],
        "MATCH (seed:Event)-[:INVOLVES]->(n:Entity {id: $entity_id})": [{"id": "evt1"}],
        "MATCH (seed:Event)-[:ABOUT]->(t:Topic {name: $topic})": [{"id": "evt1"}],
        "seed.date >= date($start)": [{"id": "evt1"}],
        "MATCH path = (seed)-[:LINKED_TO*": [
            {
                "event_ids": ["evt1", "evt2"],
                "links": [
                    {
                        "from_id": "evt1",
                        "to_id": "evt2",
                        "confidence": 0.9,
                        "reason": "shared_entities",
                    }
                ],
            }
        ],
        "UNWIND $ids AS id": [
            event_row("evt1", dt.date(2026, 3, 1)),
            event_row("evt2", dt.date(2026, 3, 2)),
        ],
        "MATCH (e:Event {id: $id})": [event_row("evt1", dt.date(2026, 3, 1))],
        "SKIP $offset LIMIT $limit": [event_row("evt1", dt.date(2026, 3, 1))],
    }


def make_client(response_map: dict[str, Any] | None = None) -> TestClient:
    app = create_app(client=FakeApiClient(response_map or responses()), config=TEST_CONFIG)
    return TestClient(app)


def test_health_returns_ok():
    with make_client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["neo4j"]["connected"] is True
    assert body["neo4j"]["server_version"] == "5.26.32"


def test_event_by_id_returns_model():
    with make_client() as client:
        response = client.get("/events/test_unit_evt_1")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "evt1"
    assert body["date"] == "2026-03-01"
    assert body["article_id"] == "test_unit_art"


def test_missing_event_returns_404():
    response_map = responses()
    response_map["MATCH (e:Event {id: $id})"] = []

    with make_client(response_map) as client:
        response = client.get("/events/not_there")

    assert response.status_code == 404


def test_events_in_date_range_returns_list():
    with make_client() as client:
        response = client.get("/events?start=2026-03-01&end=2026-03-31")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == "evt1"


def test_reversed_date_range_returns_422():
    with make_client() as client:
        response = client.get("/events?start=2026-04-01&end=2026-03-01")

    assert response.status_code == 422


def test_entity_chain_returns_model():
    with make_client() as client:
        response = client.get("/chains/entity?name=Test+Fixture+Bank&min_confidence=0.5&depth=2")

    assert response.status_code == 200
    body = response.json()
    assert body["match_mode"] == "exact"
    assert [event["id"] for event in body["events"]] == ["evt1", "evt2"]
    assert body["links"][0]["confidence"] == 0.9


def test_topic_chain_returns_model():
    with make_client() as client:
        response = client.get("/chains/topic?topic=unit+topic")

    assert response.status_code == 200
    assert response.json()["events"][0]["id"] == "evt1"


def test_date_range_chain_returns_model():
    with make_client() as client:
        response = client.get("/chains/date-range?start=2026-03-01&end=2026-03-31")

    assert response.status_code == 200
    assert response.json()["events"][0]["id"] == "evt1"


def test_invalid_confidence_returns_422():
    with make_client() as client:
        response = client.get("/chains/entity?name=x&min_confidence=2.0")

    assert response.status_code == 422


def test_openapi_lists_the_stable_paths():
    with make_client() as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/health" in paths
    assert "/events/{event_id}" in paths
    assert "/chains/entity" in paths
    assert "/chains/topic" in paths
    assert "/chains/date-range" in paths


def make_authed_client(**kwargs) -> TestClient:
    app = create_app(client=FakeApiClient(responses()), config=TEST_CONFIG, api_keys=["key-one", "key-two"], **kwargs)
    return TestClient(app)


def test_protected_routes_require_a_valid_api_key():
    with make_authed_client() as client:
        assert client.get("/events/evt_1").status_code == 401
        assert client.get("/events/evt_1", headers={"X-API-Key": "wrong"}).status_code == 401
        assert client.get("/events/evt_1", headers={"X-API-Key": "key-two"}).status_code == 200


def test_health_stays_public_with_auth_enabled():
    with make_authed_client() as client:
        assert client.get("/health").status_code == 200


def test_real_app_refuses_to_start_without_api_keys(monkeypatch):
    monkeypatch.delenv("API_KEYS", raising=False)
    monkeypatch.delenv("API_AUTH_DISABLED", raising=False)
    app = create_app(api_keys=[])
    with pytest.raises(RuntimeError, match="API_KEYS"):
        with TestClient(app):
            pass


def test_cors_allows_only_configured_origins():
    with make_authed_client(cors_origins=["https://app.example"]) as client:
        ok = client.get("/health", headers={"Origin": "https://app.example"})
        other = client.get("/health", headers={"Origin": "https://evil.example"})
    assert ok.headers.get("access-control-allow-origin") == "https://app.example"
    assert "access-control-allow-origin" not in other.headers
