from __future__ import annotations

import copy
import datetime as dt
from pathlib import Path

import pytest

from common.schema import Event, ExtractedEvent, Topic
from graphdb.config import load_neo4j_config
from graphdb.connection import Neo4jClient
from graphdb.writer import PipelineWriter, graph_counts, load_pipeline_output

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).parent / "fixtures" / "pipeline_output.json"
EXTRA_EVENT_ID = "test_fixture_evt_1b"


def _node_ids(output) -> set[str]:
    ids = {result.article.id for result in output.results}
    ids |= {entity.id for result in output.results for entity in result.entities}
    for result in output.results:
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


def _precedes_pairs(client: Neo4jClient, event_ids: set[str]) -> list[tuple[str, str]]:
    rows = client.run(
        "MATCH (a:Event)-[:PRECEDES]->(b:Event) "
        "WHERE a.id IN $ids AND b.id IN $ids "
        "RETURN a.id AS a, b.id AS b ORDER BY a.date, a.id, b.date, b.id",
        {"ids": sorted(event_ids)},
    )
    return [(str(row["a"]), str(row["b"])) for row in rows]


def _with_out_of_order_event(output):
    modified = copy.deepcopy(output)
    result = modified.results[0]
    bank = next(entity for entity in result.entities if entity.id == "test_fixture_ent_bank")
    result.events.append(
        ExtractedEvent(
            event=Event(
                id=EXTRA_EVENT_ID,
                description="Test Fixture Bank issued an interim statement",
                date=dt.date(2026, 2, 15),
                type="policy_change",
                date_source="explicit",
            ),
            entities=[bank],
            topic=Topic(name="test-fixture interest rates"),
            source_text="Test Fixture Bank issued an interim statement on 15 February 2026.",
        )
    )
    return modified


def test_writer_is_idempotent_and_rebuilds_precedes():
    config = load_neo4j_config()
    client = Neo4jClient(config)

    original = load_pipeline_output(FIXTURE)
    node_ids = _node_ids(original)
    topic_names = _topic_names(original)
    all_node_ids = node_ids | {EXTRA_EVENT_ID}
    all_event_ids = {
        extracted.event.id
        for result in original.results
        for extracted in result.events
    } | {EXTRA_EVENT_ID}

    try:
        _cleanup(client, all_node_ids, topic_names)
        writer = PipelineWriter(client)

        first = writer.write(original)
        after_first = graph_counts(client)

        second = writer.write(original)
        after_second = graph_counts(client)

        assert first.counts.nodes_created == 12
        assert first.counts.nodes_matched == 0
        assert first.counts.relationships_created == 26
        assert first.counts.relationships_matched == 0
        assert first.counts.precedes_rebuilt == 3

        assert second.counts.nodes_created == 0
        assert second.counts.nodes_matched == 12
        assert second.counts.relationships_created == 0
        assert second.counts.relationships_matched == 26
        assert second.counts.precedes_rebuilt == 3

        assert after_first == after_second

        expected_chain = [
            ("test_fixture_evt_4", "test_fixture_evt_1"),
            ("test_fixture_evt_1", "test_fixture_evt_2"),
            ("test_fixture_evt_2", "test_fixture_evt_3"),
        ]
        assert _precedes_pairs(client, all_event_ids) == expected_chain

        writer.write(_with_out_of_order_event(original))

        out_of_order_chain = [
            ("test_fixture_evt_4", EXTRA_EVENT_ID),
            (EXTRA_EVENT_ID, "test_fixture_evt_1"),
            ("test_fixture_evt_1", "test_fixture_evt_2"),
            ("test_fixture_evt_2", "test_fixture_evt_3"),
        ]
        assert _precedes_pairs(client, all_event_ids) == out_of_order_chain
    finally:
        try:
            _cleanup(client, all_node_ids, topic_names)
        finally:
            client.close()
