"""Retention, size guard and backfill against the throwaway test database."""

import datetime as dt

import pytest

from common.schema import Article, PipelineOutput
from graphdb.capacity import GraphFullError, GraphLimits, apply_retention, check_capacity, graph_size, retention_preview
from graphdb.config import load_neo4j_config
from graphdb.connection import Neo4jClient
from graphdb.writer import PipelineWriter
from pipeline.extract import SpacyExtractor
from pipeline.ingest import RawArticle
from pipeline.ingest_job import IngestConfig, IngestQuery, run_ingest

pytestmark = pytest.mark.integration
TODAY = dt.date(2024, 9, 30)


def raw(article_id, day, text):
    return RawArticle(Article(article_id, text[:40], day, "t", f"https://example.com/{article_id}"), text)


OLD = raw("old", dt.date(2024, 6, 1), "The Bank of England kept interest rates on hold in June 2024 as inflation fell.")
PINNED = raw("pinned", dt.date(2024, 6, 2), "Opec agreed to cut oil production in June 2024 as crude prices slid.")
RECENT = raw("recent", dt.date(2024, 9, 19), "The Bank of England held interest rates at 5% in September 2024.")


def write(client, *raws):
    extractor = SpacyExtractor()
    PipelineWriter(client).write(PipelineOutput(results=[extractor.extract(r.article, r.text) for r in raws]))


def test_retention_deletes_expired_unpinned_articles_and_their_orphans():
    with Neo4jClient(load_neo4j_config()) as client:
        write(client, OLD, PINNED, RECENT)
        client.run("MATCH (a:Article {id: 'pinned'}) SET a.pinned = true")
        before = graph_size(client)
        assert retention_preview(client, 30, TODAY)["articles"] == 1

        result = apply_retention(client, 30, TODAY)
        assert result["articles"] == 1 and result["events"] >= 1
        ids = {r["id"] for r in client.run("MATCH (a:Article) RETURN a.id AS id")}
        assert ids == {"pinned", "recent"}
        assert client.run("MATCH (n) WHERE (n:Entity OR n:Topic) AND NOT (n)--() RETURN count(n) AS n")[0]["n"] == 0
        events = client.run("MATCH (e:Event) RETURN count(e) AS n")[0]["n"]
        assert client.run("MATCH ()-[r:PRECEDES]->() RETURN count(r) AS n")[0]["n"] == events - 1
        assert graph_size(client).nodes < before.nodes
        assert apply_retention(client, 30, TODAY)["articles"] == 0  # idempotent


def test_size_guard_refuses_to_write_when_nearly_full():
    with Neo4jClient(load_neo4j_config()) as client:
        write(client, RECENT)
        size = graph_size(client)
        check_capacity(client, GraphLimits(size.nodes * 10, size.relationships * 10))  # plenty of room
        with pytest.raises(GraphFullError):
            check_capacity(client, GraphLimits(size.nodes, size.relationships * 10))


class ListSource:
    def __init__(self, raws):
        self.raws = raws

    def load(self):
        return list(self.raws)


def test_backfill_since_is_clamped_to_retention_and_uses_every_source():
    with Neo4jClient(load_neo4j_config()) as client:
        config = IngestConfig(queries=(IngestQuery(""),), retention_days=30, lookback_days=30)
        seen = []

        def make_source(query, start, end):
            seen.append(("guardian", start, end))
            return ListSource([RECENT])

        def extra(start, end):
            seen.append(("wikipedia", start, end))
            return [ListSource([PINNED])]

        summary = run_ingest(config, make_source, SpacyExtractor(), client, PipelineWriter(client).write,
                             today=TODAY, since=dt.date(2024, 1, 1), extra_sources=extra)
        floor = TODAY - dt.timedelta(days=30)
        assert seen == [("guardian", floor, TODAY), ("wikipedia", floor, TODAY)]
        assert summary.from_date == floor.isoformat() and summary.new_articles == 2 and summary.written
        assert summary.graph["nodes"] > 0 and 0 < summary.graph["usage"] < 1
