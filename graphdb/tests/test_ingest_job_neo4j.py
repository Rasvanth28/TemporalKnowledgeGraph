"""Incremental ingestion against the throwaway test database (wiped before each test)."""

import datetime

import pytest

from common.schema import Article
from graphdb.config import load_neo4j_config
from graphdb.connection import Neo4jClient
from graphdb.writer import PipelineWriter
from pipeline.extract import SpacyExtractor
from pipeline.ingest import RawArticle
from pipeline.ingest_job import IngestConfig, IngestQuery, run_ingest

pytestmark = pytest.mark.integration

RAISE = RawArticle(Article("art_raise", "Bank of England raises interest rates", datetime.date(2024, 3, 1), "t", "u1"),
                   "The Bank of England raised interest rates in March 2024. Andrew Bailey warned inflation in Britain remained high.")
STORM = RawArticle(Article("art_storm", "Storms hit Japan", datetime.date(2024, 3, 20), "t", "u2"),
                   "Storms hit Japan on 20 March 2024, cutting power to Tokyo.")
HOLD = RawArticle(Article("art_hold", "Bank of England holds interest rates", datetime.date(2024, 4, 10), "t", "u3"),
                  "The Bank of England kept interest rates on hold in April 2024 as inflation in Britain slowed.")


class ListSource:
    def __init__(self, raws):
        self.raws = raws

    def load(self):
        return list(self.raws)


def _ingest(client, raws, today):
    config = IngestConfig(queries=(IngestQuery("q"),), lookback_days=90)
    return run_ingest(config, lambda q, start, end: ListSource(raws), SpacyExtractor(), client,
                      PipelineWriter(client).write, today=today)


def test_second_run_skips_known_articles_and_links_to_existing_events():
    with Neo4jClient(load_neo4j_config()) as client:
        first = _ingest(client, [RAISE, STORM], datetime.date(2024, 3, 25))
        assert first.from_date == "2024-02-24"  # empty graph: initial_days back
        assert first.new_articles == 2 and first.written

        second = _ingest(client, [RAISE, STORM, HOLD], datetime.date(2024, 4, 12))
        assert second.from_date == "2024-03-18"  # newest stored article minus overlap
        assert second.fetched == 3 and second.new_articles == 1
        assert second.existing_events_considered > 0
        assert second.links_to_existing >= 1

        rows = client.run(
            "MATCH (a:Event)<-[:DESCRIBES]-(:Article {id: 'art_raise'}), (b:Event)<-[:DESCRIBES]-(:Article {id: 'art_hold'}) "
            "MATCH (a)-[r:LINKED_TO]->(b) RETURN count(r) AS n"
        )
        assert rows[0]["n"] >= 1
        storm_links = client.run(
            "MATCH (:Article {id: 'art_storm'})-[:DESCRIBES]->(e:Event)-[r:LINKED_TO]-() RETURN count(r) AS n"
        )
        assert storm_links[0]["n"] == 0

        third = _ingest(client, [RAISE, STORM, HOLD], datetime.date(2024, 4, 12))
        assert third.new_articles == 0 and not third.written
