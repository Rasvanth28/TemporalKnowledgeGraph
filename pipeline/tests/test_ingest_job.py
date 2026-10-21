import datetime
import json

import pytest

from pipeline.ingest_job import IngestConfig, IngestQuery, extracted_from_graph, fetch_window, load_ingest_config

CONFIG = IngestConfig(queries=(IngestQuery("q"),), initial_days=30, overlap_days=2)
TODAY = datetime.date(2026, 10, 21)


def test_fetch_window_starts_before_newest_stored_article():
    assert fetch_window(datetime.date(2026, 10, 15), TODAY, CONFIG) == (datetime.date(2026, 10, 13), TODAY)

def test_fetch_window_for_empty_graph_uses_initial_days():
    assert fetch_window(None, TODAY, CONFIG) == (datetime.date(2026, 9, 21), TODAY)

def test_fetch_window_never_starts_in_the_future():
    assert fetch_window(datetime.date(2026, 10, 30), TODAY, CONFIG)[0] == TODAY

def test_load_ingest_config(tmp_path):
    path = tmp_path / "q.json"
    path.write_text(json.dumps({"queries": [{"query": "a", "section": "business"}, {"query": "b"}], "lookback_days": 60}))
    config = load_ingest_config(path)
    assert config.queries == (IngestQuery("a", "business"), IngestQuery("b"))
    assert config.lookback_days == 60 and config.max_per_query == 20

def test_load_ingest_config_requires_queries(tmp_path):
    path = tmp_path / "q.json"
    path.write_text(json.dumps({"queries": []}))
    with pytest.raises(ValueError):
        load_ingest_config(path)

def test_checked_in_ingest_config_is_valid():
    assert load_ingest_config("config/ingest_queries.json").queries

def test_extracted_from_graph_round_trips_event_fields():
    row = {"id": "e1", "description": "d", "date": "2024-03-01", "type": "general", "date_source": "inferred",
           "source_text": "s", "article_id": "a1", "entities": [{"id": "x", "name": "X", "type": "ORG"}], "topic": "t"}
    article_id, extracted = extracted_from_graph(row)
    assert article_id == "a1"
    assert extracted.event.date == datetime.date(2024, 3, 1) and extracted.event.date_source == "inferred"
    assert extracted.entities[0].name == "X" and extracted.topic.name == "t" and extracted.source_text == "s"


def test_load_ingest_config_everything_wikipedia_retention(tmp_path):
    path = tmp_path / "q.json"
    path.write_text(json.dumps({"queries": [{"query": ""}], "wikipedia_current_events": True, "retention_days": 30,
                                "graph_limits": {"max_nodes": 1000, "max_relationships": 2000}}))
    config = load_ingest_config(path)
    assert config.queries == (IngestQuery(""),) and config.wikipedia and config.retention_days == 30
    assert (config.max_nodes, config.max_relationships) == (1000, 2000)


def test_wikipedia_alone_is_a_valid_config(tmp_path):
    path = tmp_path / "q.json"
    path.write_text(json.dumps({"wikipedia_current_events": True}))
    assert load_ingest_config(path).queries == ()
