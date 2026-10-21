from __future__ import annotations

import datetime as dt
from typing import Any, Callable

import pytest

from graphdb.queries import (
    date_key,
    event_by_id,
    events_in_date_range,
    chain_by_date_range,
    chain_by_entity,
    chain_by_topic,
    find_entity,
)


class FakeQueryClient:
    def __init__(self, responses: dict[str, Any]):
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: str, parameters=None, database=None):
        self.calls.append((query, dict(parameters or {})))
        for needle, response in self.responses.items():
            if needle in query:
                return response(parameters or {}) if callable(response) else response
        raise AssertionError(f"unexpected query: {query}")


def event_row(
    event_id: str,
    date: dt.date,
    article_id: str = "test_unit_art",
    entities: list[dict[str, Any]] | None = None,
    topics: list[str | None] | None = None,
) -> dict[str, Any]:
    return {
        "id": event_id,
        "description": f"description {event_id}",
        "date": date,
        "type": "general",
        "date_source": "explicit",
        "article_ids": [article_id],
        "entities": entities
        if entities is not None
        else [{"id": "test_unit_ent", "name": "Unit Entity", "type": "ORG"}],
        "topics": topics if topics is not None else ["unit topic"],
    }


def test_date_key_matches_pipeline_contract():
    assert date_key(dt.date(1970, 1, 2)) == 1
    assert date_key("1970-01-02") == 1


def test_normalize_exact_entity_match():
    client = FakeQueryClient(
        {
            "MATCH (n:Entity {name: $name})": [
                {"id": "ent1", "name": "Test Fixture Bank", "type": "ORG"}
            ],
        }
    )

    entity, mode, ambiguous = find_entity(client, "The Test Fixture Bank")

    assert entity == {"id": "ent1", "name": "Test Fixture Bank", "type": "ORG"}
    assert mode == "exact"
    assert ambiguous is False


def test_normalize_falls_back_to_non_indexed_scan():
    client = FakeQueryClient(
        {
            "MATCH (n:Entity {name: $name})": [],
            "toLower(n.name) = toLower($name)": [
                {"id": "ent1", "name": "Test Fixture Bank", "type": "ORG"}
            ],
        }
    )

    entity, mode, ambiguous = find_entity(client, "test fixture bank")

    assert entity is not None
    assert mode == "case_insensitive_scan"
    assert ambiguous is False


def test_event_by_id_converts_dates_and_filters_nulls():
    client = FakeQueryClient(
        {
            "MATCH (e:Event {id: $id})": [
                event_row(
                    "evt1",
                    dt.date(2026, 3, 1),
                    entities=[
                        {"id": "ent1", "name": "Unit Entity", "type": "ORG"},
                        {"id": None, "name": None, "type": None},
                    ],
                    topics=["unit topic", None],
                )
            ]
        }
    )

    event = event_by_id(client, "evt1")

    assert event is not None
    assert event["date"] == "2026-03-01"
    assert event["date_key"] == date_key(dt.date(2026, 3, 1))
    assert event["entities"] == [{"id": "ent1", "name": "Unit Entity", "type": "ORG"}]
    assert event["topics"] == ["unit topic"]


def test_event_by_id_returns_none_when_missing():
    client = FakeQueryClient({"MATCH (e:Event {id: $id})": []})
    assert event_by_id(client, "missing") is None


def test_events_in_date_range_returns_plain_rows():
    client = FakeQueryClient(
        {
            "SKIP $offset LIMIT $limit": [
                event_row("evt1", dt.date(2026, 3, 1)),
                event_row("evt2", dt.date(2026, 3, 2)),
            ]
        }
    )

    rows = events_in_date_range(client, "2026-03-01", "2026-03-31")

    assert [row["id"] for row in rows] == ["evt1", "evt2"]
    assert all(row["date_key"] is not None for row in rows)
    query, parameters = client.calls[0]
    assert parameters["start"] == "2026-03-01"
    assert parameters["end"] == "2026-03-31"


def test_events_in_date_range_rejects_reversed_range():
    client = FakeQueryClient({})
    with pytest.raises(ValueError, match="start must be on or before end"):
        events_in_date_range(client, "2026-04-01", "2026-03-01")


def test_chain_by_entity_merges_seeds_and_paths():
    client = FakeQueryClient(
        {
            "MATCH (n:Entity {name: $name})": [
                {"id": "ent1", "name": "Test Fixture Bank", "type": "ORG"}
            ],
            "MATCH (seed:Event)-[:INVOLVES]->(n:Entity {id: $entity_id})": [
                {"id": "evt1"}
            ],
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
        }
    )

    result = chain_by_entity(client, "Test Fixture Bank", min_confidence=0.5, depth=2, limit=10)

    assert result["match_mode"] == "exact"
    assert [event["id"] for event in result["events"]] == ["evt1", "evt2"]
    assert result["links"] == [
        {
            "from_event_id": "evt1",
            "to_event_id": "evt2",
            "confidence": 0.9,
            "reason": "shared_entities",
            "from_date": "2026-03-01",
            "to_date": "2026-03-02",
        }
    ]
    assert result["truncated"] is False


def test_chain_by_entity_returns_empty_for_unknown_entity():
    client = FakeQueryClient({"MATCH (n:Entity {name: $name})": [], "toLower": []})

    result = chain_by_entity(client, "Missing Entity")

    assert result["entity"] is None
    assert result["match_mode"] == "none"
    assert result["events"] == []


def test_chain_by_topic_uses_topic_seeds():
    client = FakeQueryClient(
        {
            "MATCH (seed:Event)-[:ABOUT]->(t:Topic {name: $topic})": [{"id": "evt1"}],
            "MATCH path = (seed)-[:LINKED_TO*": [],
            "UNWIND $ids AS id": [event_row("evt1", dt.date(2026, 3, 1), topics=["unit topic"])],
        }
    )

    result = chain_by_topic(client, "unit topic")

    assert result["match_mode"] == "exact"
    assert [event["id"] for event in result["events"]] == ["evt1"]
    assert result["links"] == []


def test_chain_by_date_range_uses_date_seeds():
    client = FakeQueryClient(
        {
            "seed.date >= date($start)": [{"id": "evt1"}],
            "MATCH path = (seed)-[:LINKED_TO*": [],
            "UNWIND $ids AS id": [event_row("evt1", dt.date(2026, 3, 1))],
        }
    )

    result = chain_by_date_range(client, "2026-03-01", "2026-03-31")

    assert result["query"]["start"] == "2026-03-01"
    assert result["match_mode"] == "exact"
    assert [event["id"] for event in result["events"]] == ["evt1"]


def test_limit_clamps_to_maximum():
    client = FakeQueryClient({"SKIP $offset LIMIT $limit": []})

    events_in_date_range(client, "2026-01-01", "2026-01-31", limit=10_000)

    assert client.calls[0][1]["limit"] == 1000


def test_invalid_query_parameters_are_rejected():
    client = FakeQueryClient({})

    with pytest.raises(ValueError, match="limit must be a positive integer"):
        events_in_date_range(client, "2026-01-01", "2026-01-31", limit=0)
    with pytest.raises(ValueError, match="offset must be a non-negative integer"):
        events_in_date_range(client, "2026-01-01", "2026-01-31", offset=-1)
    with pytest.raises(ValueError, match="min_confidence must be between"):
        chain_by_entity(client, "x", min_confidence=2.0)
    with pytest.raises(ValueError, match="depth must be a positive integer"):
        chain_by_entity(client, "x", depth=0)
