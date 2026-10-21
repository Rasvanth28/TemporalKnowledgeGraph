from __future__ import annotations

import json
from pathlib import Path

import pytest

from graphdb.config import load_neo4j_config
from graphdb.connection import Neo4jClient
from graphdb.queries import (
    chain_by_date_range,
    chain_by_entity,
    chain_by_topic,
    event_by_id,
    events_in_date_range,
    explain_events_in_date_range,
)
from graphdb.writer import PipelineWriter, load_pipeline_output

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).parent / "fixtures" / "pipeline_output.json"


def _node_ids(output) -> set[str]:
    ids = {result.article.id for result in output.results}
    for result in output.results:
        ids |= {entity.id for entity in result.entities}
        for extracted in result.events:
            ids.add(extracted.event.id)
            ids |= {entity.id for entity in extracted.entities}
    return ids


def _topic_names(output) -> set[str]:
    return {
        extracted.topic.name
        for result in output.results
        for extracted in result.events
    }


def _cleanup(client: Neo4jClient, node_ids: set[str], topic_names: set[str]) -> None:
    client.run("MATCH (n) WHERE n.id IN $ids DETACH DELETE n", {"ids": sorted(node_ids)})
    client.run("MATCH (t:Topic) WHERE t.name IN $names DETACH DELETE t", {"names": sorted(topic_names)})


def test_query_round_trip_and_index_evidence():
    config = load_neo4j_config()
    client = Neo4jClient(config)
    output = load_pipeline_output(FIXTURE)
    node_ids = _node_ids(output)
    topic_names = _topic_names(output)

    try:
        _cleanup(client, node_ids, topic_names)
        PipelineWriter(client).write(output)

        events = events_in_date_range(client, "2026-01-01", "2026-12-31")
        assert [event["id"] for event in events] == [
            "test_fixture_evt_4",
            "test_fixture_evt_1",
            "test_fixture_evt_2",
            "test_fixture_evt_3",
        ]

        event = event_by_id(client, "test_fixture_evt_1")
        assert event is not None
        assert event["date"] == "2026-03-01"
        assert event["article_id"] == "test_fixture_art_1"
        assert {entity["id"] for entity in event["entities"]} == {"test_fixture_ent_bank"}

        entity_chain = chain_by_entity(client, "Test Fixture Bank")
        assert entity_chain["match_mode"] == "exact"
        assert len(entity_chain["events"]) == 4
        assert len(entity_chain["links"]) == 4

        topic_chain = chain_by_topic(client, "test-fixture interest rates")
        assert topic_chain["match_mode"] == "exact"
        assert len(topic_chain["events"]) == 4
        assert len(topic_chain["links"]) == 4

        range_chain = chain_by_date_range(client, "2026-01-01", "2026-03-15")
        assert len(range_chain["events"]) == 4

        plan_text = json.dumps(explain_events_in_date_range(client, "2026-01-01", "2026-12-31"), default=str)
        assert "event_date" in plan_text
    finally:
        try:
            _cleanup(client, node_ids, topic_names)
        finally:
            client.close()
