"""Prompt search against the throwaway test database with the real embedding model."""

import datetime as dt

import pytest

from common.embed import get_embedder
from common.schema import Article, PipelineOutput
from graphdb.config import load_neo4j_config
from graphdb.connection import Neo4jClient
from graphdb.search import search_graph
from graphdb.search_index import embed_missing_events, ensure_search_indexes
from graphdb.writer import PipelineWriter
from pipeline.extract import SpacyExtractor
from pipeline.link import link_events

pytestmark = pytest.mark.integration

ARTICLES = [
    ("a_raise", "Bank of England raises interest rates", dt.date(2024, 3, 1),
     "The Bank of England raised interest rates in March 2024. Andrew Bailey warned inflation in Britain remained high."),
    ("a_hold", "Bank of England holds interest rates", dt.date(2024, 4, 10),
     "The Bank of England kept interest rates on hold in April 2024 as inflation in Britain slowed."),
    ("a_opec", "Opec cuts oil output", dt.date(2024, 6, 2),
     "Opec agreed to cut oil production in June 2024 as crude prices fell in Saudi Arabia."),
    ("a_storm", "Storms hit Japan", dt.date(2024, 3, 20),
     "Storms hit Japan on 20 March 2024, cutting power to Tokyo."),
]


@pytest.fixture
def client():
    with Neo4jClient(load_neo4j_config()) as neo4j:
        extractor = SpacyExtractor()
        results = [extractor.extract(Article(i, t, d, "test", f"https://example.com/{i}"), text)
                   for i, t, d, text in ARTICLES]
        PipelineWriter(neo4j).write(PipelineOutput(results=results, links=link_events(results)))
        embedder = get_embedder()
        ensure_search_indexes(neo4j, embedder.dims)
        assert embed_missing_events(neo4j, embedder) > 0
        assert embed_missing_events(neo4j, embedder) == 0  # idempotent
        yield neo4j


def labels(result, kind):
    return {n["label"] for n in result["nodes"] if n["kind"] == kind}


def test_entity_prompt_builds_a_graph_around_that_entity(client):
    result = search_graph(client, "what did the Bank of England do with rates?", get_embedder())
    assert [e["name"] for e in result["interpretation"]["entities"]] == ["Bank of England"]
    assert "Bank of England" in labels(result, "entity")
    assert not any("Storms" in label or "Opec" in label for label in labels(result, "event"))
    matched = [n for n in result["nodes"] if n["kind"] == "entity" and n["matched"]]
    assert [n["label"] for n in matched] == ["Bank of England"]
    assert any(e["kind"] == "involves" for e in result["edges"])


def test_meaning_search_finds_events_without_shared_words(client):
    result = search_graph(client, "who drove UK borrowing costs?", get_embedder())
    events = [n for n in result["nodes"] if n["kind"] == "event"]
    top = max(events, key=lambda n: n["relevance"])
    assert top["article_id"] in {"a_raise", "a_hold"}


def test_date_range_filters_events(client):
    result = search_graph(client, "oil production in June 2024", get_embedder())
    assert result["interpretation"]["start"] == "2024-06-01"
    dates = {n["date"] for n in result["nodes"] if n["kind"] == "event"}
    assert dates and all(d.startswith("2024-06") for d in dates)


def test_off_topic_prompts_return_an_empty_graph_not_noise(client):
    for prompt in ["zzqx florp", "recipe for chocolate cake"]:
        result = search_graph(client, prompt, get_embedder())
        assert result["nodes"] == [] and result["edges"] == [], prompt


def test_search_still_works_before_search_indexes_exist():
    # Fresh deploy: ingestion has not created the full-text/vector indexes yet.
    with Neo4jClient(load_neo4j_config()) as neo4j:
        extractor = SpacyExtractor()
        i, t, d, text = ARTICLES[0]
        result = extractor.extract(Article(i, t, d, "test", "u"), text)
        PipelineWriter(neo4j).write(PipelineOutput(results=[result]))
        for name in ("event_text", "event_embedding"):
            neo4j.run(f"DROP INDEX {name} IF EXISTS")
        found = search_graph(neo4j, "Bank of England interest rates", get_embedder())
        assert "Bank of England" in labels(found, "entity")
