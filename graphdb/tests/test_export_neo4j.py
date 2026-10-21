from __future__ import annotations

import csv
from pathlib import Path

import pytest

from graphdb.config import load_neo4j_config
from graphdb.connection import Neo4jClient
from graphdb.export import EVENT_KEY_COLUMNS, export_event_keys, export_from_graph
from graphdb.queries import date_key
from graphdb.tests.test_queries_neo4j import (  # noqa: F401 - pytest fixture usage
    FIXTURE,
    _cleanup,
    _node_ids,
    _topic_names,
)
from graphdb.writer import PipelineWriter, load_pipeline_output

pytestmark = pytest.mark.integration


def _expected_rows(output) -> list[dict[str, object]]:
    rows = [
        {
            "event_id": extracted.event.id,
            "date_key": date_key(extracted.event.date),
            "date": extracted.event.date.isoformat(),
            "date_source": extracted.event.date_source,
            "type": extracted.event.type,
            "article_id": result.article.id,
        }
        for result in output.results
        for extracted in result.events
    ]
    rows.sort(key=lambda item: (int(item["date_key"]), str(item["event_id"])))
    return rows


def test_export_from_populated_graph_matches_contract(tmp_path: Path):
    config = load_neo4j_config()
    client = Neo4jClient(config)
    output = load_pipeline_output(FIXTURE)
    node_ids = _node_ids(output)
    topic_names = _topic_names(output)

    try:
        _cleanup(client, node_ids, topic_names)
        PipelineWriter(client).write(output)

        rows = [
            row
            for row in export_event_keys(client)
            if row["event_id"] in {item["event_id"] for item in _expected_rows(output)}
        ]
        assert rows == _expected_rows(output)

        path = tmp_path / "graph_event_keys.csv"
        assert export_from_graph(client, path) >= len(rows)
        with open(path, newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            assert reader.fieldnames == EVENT_KEY_COLUMNS
            written = [item for item in reader if item["event_id"] in {r["event_id"] for r in rows}]
        expected_written = [
            {key: str(value) for key, value in row.items()}
            for row in rows
        ]
        assert written == expected_written
    finally:
        try:
            _cleanup(client, node_ids, topic_names)
        finally:
            client.close()
