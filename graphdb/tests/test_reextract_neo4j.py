"""Re-extraction migration against the throwaway test database."""

import dataclasses
import datetime as dt

import pytest

from common.schema import Article, Entity, PipelineOutput
from graphdb.config import load_neo4j_config
from graphdb.connection import Neo4jClient
from graphdb.writer import PipelineWriter
from pipeline.extract import SpacyExtractor, get_id
from pipeline.ingest import RawArticle
from pipeline.reextract import apply_reextract, plan_reextract

pytestmark = pytest.mark.integration

CUT = RawArticle(Article("a_cut", "Bank of England cuts rates", dt.date(2024, 8, 1), "t", "https://example.com/cut"),
                 "The Bank of England has cut interest rates for the first time since the 2008 crisis.")
HOLD = RawArticle(Article("a_hold", "Bank of England holds rates", dt.date(2024, 8, 20), "t", "https://example.com/hold"),
                  "The Bank of England kept interest rates on hold in August 2024.")
TEXT = {r.article.id: r for r in (CUT, HOLD)}


def _old_style(result):
    """What the previous extractor stored: the event dated by "the 2008 crisis", with the id that implies."""
    (extracted,) = result.events
    wrong = dt.date(2008, 1, 1)
    event = dataclasses.replace(extracted.event, date=wrong, date_source="explicit",
                                id=get_id(result.article.id + extracted.event.description + str(wrong)))
    stray = Entity(id="old_only", name="Old Only Entity", type="ORG")
    old = dataclasses.replace(extracted, event=event, entities=extracted.entities + [stray])
    return dataclasses.replace(result, events=[old], entities=result.entities + [stray])


def test_reextract_replaces_misdated_events_and_is_idempotent():
    extractor = SpacyExtractor()
    with Neo4jClient(load_neo4j_config()) as client:
        writer = PipelineWriter(client)
        writer.write(PipelineOutput(results=[_old_style(extractor.extract(CUT.article, CUT.text)),
                                             extractor.extract(HOLD.article, HOLD.text)]))
        assert client.run("MATCH (e:Event) WHERE e.date.year = 2008 RETURN count(e) AS n")[0]["n"] == 1

        report, results = plan_reextract(client, extractor, lambda article_id, url: TEXT.get(article_id))
        assert [c.article_id for c in report.changes] == ["a_cut"]
        assert report.events_removed == 1 and report.events_added == 1
        assert report.changes[0].redated == [("2008-01-01", "2024-08-01")]

        # The old event also carried an entity nobody else uses; it must not be left floating.
        client.run("MATCH (a:Article {id: 'a_cut'}) MATCH (n:Entity {id: 'old_only'}) MATCH (a)-[r:MENTIONS]->(n) DELETE r")
        apply_reextract(client, report, results, writer.write)

        rows = client.run("MATCH (:Article {id: 'a_cut'})-[:DESCRIBES]->(e:Event) RETURN toString(e.date) AS date, e.date_source AS src")
        assert rows == [{"date": "2024-08-01", "src": "inferred"}]
        assert client.run("MATCH (e:Event) WHERE e.date.year = 2008 RETURN count(e) AS n")[0]["n"] == 0
        assert client.run("MATCH (n:Entity {id: 'old_only'}) RETURN count(n) AS n")[0]["n"] == 0
        linked = client.run("MATCH (:Article {id: 'a_cut'})-[:DESCRIBES]->(:Event)-[r:LINKED_TO]->(:Event)<-[:DESCRIBES]-(:Article {id: 'a_hold'}) RETURN count(r) AS n")
        assert linked[0]["n"] == 1
        assert client.run("MATCH ()-[r:PRECEDES]->() RETURN count(r) AS n")[0]["n"] == 1

        again, _ = plan_reextract(client, extractor, lambda article_id, url: TEXT.get(article_id))
        assert again.changes == [] and again.missing_text == []


def test_articles_without_text_are_reported_and_left_alone():
    extractor = SpacyExtractor()
    with Neo4jClient(load_neo4j_config()) as client:
        PipelineWriter(client).write(PipelineOutput(results=[extractor.extract(CUT.article, CUT.text)]))
        report, results = plan_reextract(client, extractor, lambda article_id, url: None)
        assert report.missing_text == ["a_cut"] and results == [] and report.changes == []
