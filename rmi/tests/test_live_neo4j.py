"""The C4 path end to end against the throwaway test database: export, fallback, benchmark."""

import datetime as dt

import pytest

from common.schema import Article, PipelineOutput
from graphdb.config import load_neo4j_config
from graphdb.connection import Neo4jClient
from graphdb.queries import date_key
from graphdb.writer import PipelineWriter
from pipeline.extract import SpacyExtractor
from rmi.config import RMIConfig
from rmi.date_index import DateIndex
from rmi.live import benchmark, export_event_keys, make_queries, neo4j_lower_bound

pytestmark = pytest.mark.integration

STORIES = [
    ("a1", dt.date(2024, 9, 2), "The Bank of England held interest rates at 5% on 2 September 2024."),
    ("a2", dt.date(2024, 9, 9), "Opec agreed to cut oil production on 9 September 2024 as prices slid."),
    ("a3", dt.date(2024, 9, 20), "The European Central Bank cut rates on 20 September 2024 in Frankfurt."),
]


@pytest.fixture
def client():
    with Neo4jClient(load_neo4j_config()) as client:
        extractor = SpacyExtractor()
        results = [extractor.extract(Article(i, text[:40], day, "t", f"https://example.com/{i}"), text)
                   for i, day, text in STORIES]
        PipelineWriter(client).write(PipelineOutput(results=results))
        yield client


def test_export_matches_the_graph_and_carries_publication_dates(client):
    keys = export_event_keys(client)
    assert len(keys) == client.run("MATCH (e:Event) RETURN count(e) AS n")[0]["n"] > 0
    assert {k.date_key for k in keys} >= {date_key(day) for _, day, _ in STORIES}
    assert all(k.published_key in {date_key(day) for _, day, _ in STORIES} for k in keys)
    assert [k.date_key for k in keys] == sorted(k.date_key for k in keys)


def test_neo4j_fallback_answers_the_same_lower_bounds_as_the_model(client):
    keys = export_event_keys(client)
    index = DateIndex.build(((k.date_key, k.event_id) for k in keys), fallback=neo4j_lower_bound(client))
    for key in range(int(index.days[0]) - 1, int(index.days[-1]) + 2):
        assert index.fallback(key) == index.model.lower_bound(key).index


def test_benchmark_agrees_with_neo4j_on_every_query_and_uses_the_date_index(client):
    keys = export_event_keys(client)
    result = benchmark(client, keys, make_queries(keys, 6), RMIConfig(bucket_count=2), repeats=1, warmup=1)
    assert result["correct"] == {"rmi": 6, "bisect": 6, "rmi_then_neo4j": 6}
    assert result["rmi_fallbacks"] == 0
    assert "NodeIndexSeekByRange" in result["neo4j_operators"]
