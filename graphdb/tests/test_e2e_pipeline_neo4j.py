from __future__ import annotations

import csv
from pathlib import Path

import pytest

from graphdb.config import load_neo4j_config
from graphdb.connection import Neo4jClient
from graphdb.export import EVENT_KEY_COLUMNS, export_event_keys
from graphdb.queries import event_by_id, events_in_date_range
from graphdb.writer import PipelineWriter
from pipeline.config import load_extract_config, load_link_config
from pipeline.export import write_event_keys_csv
from pipeline.extract import SpacyExtractor
from pipeline.ingest import JsonFileSource
from pipeline.run import run_pipeline

pytestmark = pytest.mark.integration

SAMPLE = Path("data/sample_articles.json")


def _collect_ids(output) -> tuple[set[str], set[str]]:
    node_ids: set[str] = set()
    topic_names: set[str] = set()
    for result in output.results:
        node_ids.add(result.article.id)
        node_ids |= {entity.id for entity in result.entities}
        for extracted in result.events:
            node_ids.add(extracted.event.id)
            node_ids |= {entity.id for entity in extracted.entities}
            topic_names.add(extracted.topic.name)
    return node_ids, topic_names


def _cleanup(client: Neo4jClient, node_ids: set[str], topic_names: set[str]) -> None:
    client.run("MATCH (n) WHERE n.id IN $ids DETACH DELETE n", {"ids": sorted(node_ids)})
    client.run("MATCH (t:Topic) WHERE t.name IN $names DETACH DELETE t", {"names": sorted(topic_names)})


def test_official_sample_round_trip(tmp_path: Path):
    config = load_neo4j_config()
    client = Neo4jClient(config)

    output = run_pipeline(
        JsonFileSource(SAMPLE),
        SpacyExtractor(load_extract_config()),
        load_link_config(),
    )
    event_ids = {extracted.event.id for result in output.results for extracted in result.events}
    node_ids, topic_names = _collect_ids(output)
    assert event_ids

    try:
        _cleanup(client, node_ids, topic_names)
        write_result = PipelineWriter(client).write(output)
        assert write_result.counts.nodes_created > 0
        assert write_result.counts.events == len(event_ids)

        for event_id in event_ids:
            event = event_by_id(client, event_id)
            assert event is not None, event_id
            assert event["id"] == event_id

        dates = sorted(extracted.event.date for result in output.results for extracted in result.events)
        ranged = events_in_date_range(client, dates[0], dates[-1])
        assert event_ids <= {event["id"] for event in ranged}

        pipeline_csv = tmp_path / "pipeline_event_keys.csv"
        write_event_keys_csv(output.results, pipeline_csv)
        with open(pipeline_csv, newline="", encoding="utf-8") as file:
            pipeline_rows = [
                row for row in csv.DictReader(file) if row["event_id"] in event_ids
            ]

        graph_rows = [
            {key: str(value) for key, value in row.items()}
            for row in export_event_keys(client)
            if row["event_id"] in event_ids
        ]
        assert EVENT_KEY_COLUMNS == list(pipeline_rows[0].keys())
        assert graph_rows == pipeline_rows
    finally:
        try:
            _cleanup(client, node_ids, topic_names)
        finally:
            client.close()
