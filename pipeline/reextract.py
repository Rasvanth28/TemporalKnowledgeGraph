"""Re-extract articles already in the graph with the current pipeline (a data migration).

Needed when extraction changes what an event *is*: event ids include the event date, so a date
fix gives some events new ids, and simply re-ingesting would leave the old copies behind.

For each article: re-extract its text, delete only the stored events whose id is no longer produced
(DETACH DELETE also removes their links), write the new results (MERGE: unchanged events are
updated in place), re-link the article's events to the rest of the graph, and remove entities/topics
left with no relationships. Running it again changes nothing.
"""

import datetime
import logging
from dataclasses import dataclass, field
from typing import Callable

from common.schema import ExtractionResult, PipelineOutput
from pipeline.config import LinkConfig
from pipeline.extract import Extractor
from pipeline.ingest import RawArticle
from pipeline.ingest_job import extracted_from_graph
from pipeline.link import link_events

log = logging.getLogger(__name__)

_STORED_ARTICLES = """
MATCH (a:Article) OPTIONAL MATCH (a)-[:DESCRIBES]->(e:Event)
RETURN a.id AS id, a.url AS url, collect(e.id) AS event_ids, collect({id: e.id, date: toString(e.date)}) AS events
ORDER BY a.id
"""
_DELETE_EVENTS = "UNWIND $ids AS id MATCH (e:Event {id: id}) DETACH DELETE e"
_DELETE_ORPHANS = """
MATCH (n) WHERE (n:Entity OR n:Topic) AND NOT (n)--()
WITH n, labels(n)[0] AS label DELETE n RETURN label, count(*) AS removed
"""


@dataclass
class ArticleChange:
    article_id: str
    removed: list[str] = field(default_factory=list)   # stored event ids no longer produced
    added: list[str] = field(default_factory=list)     # new event ids
    kept: int = 0
    redated: list[tuple[str, str]] = field(default_factory=list)  # (old date, new date) for replaced events


@dataclass
class ReextractReport:
    articles: int = 0
    missing_text: list[str] = field(default_factory=list)
    changes: list[ArticleChange] = field(default_factory=list)
    links: int = 0
    orphans_removed: int = 0
    applied: bool = False

    @property
    def events_removed(self) -> int:
        return sum(len(c.removed) for c in self.changes)

    @property
    def events_added(self) -> int:
        return sum(len(c.added) for c in self.changes)


def plan_reextract(client, extractor: Extractor, get_text: Callable[[str, str], RawArticle | None]
                   ) -> tuple[ReextractReport, list[ExtractionResult]]:
    """Re-extract every stored article; return what would change (nothing is written)."""

    report = ReextractReport()
    results: list[ExtractionResult] = []
    for row in client.run(_STORED_ARTICLES):
        report.articles += 1
        raw = get_text(row["id"], row["url"] or "")
        if raw is None:
            report.missing_text.append(row["id"])
            continue
        result = extractor.extract(raw.article, raw.text)
        results.append(result)
        old_dates = {e["id"]: e["date"] for e in row["events"] if e["id"]}
        new_ids = {e.event.id for e in result.events}
        change = ArticleChange(row["id"], removed=sorted(set(old_dates) - new_ids),
                               added=sorted(new_ids - set(old_dates)), kept=len(new_ids & set(old_dates)))
        new_dates = sorted(e.event.date.isoformat() for e in result.events if e.event.id in change.added)
        change.redated = list(zip(sorted(old_dates[i] for i in change.removed), new_dates))
        if change.removed or change.added:
            report.changes.append(change)
    return report, results


def apply_reextract(client, report: ReextractReport, results: list[ExtractionResult],
                    write: Callable[[PipelineOutput], object], link_config: LinkConfig = LinkConfig(),
                    lookback_days: int = 90) -> ReextractReport:
    """Replace changed events, re-link, and clean up. Articles without text are left untouched."""

    from graphdb.queries import events_for_linking

    stale = [event_id for change in report.changes for event_id in change.removed]
    if stale:
        client.run(_DELETE_EVENTS, {"ids": stale})

    # Link the re-extracted events to each other and to events of articles that were not re-extracted.
    redone = {r.article.id for r in results}
    dates = [e.event.date for r in results for e in r.events]
    existing = []
    if dates:
        window = (min(dates) - datetime.timedelta(days=lookback_days), max(dates))
        existing = [pair for pair in (extracted_from_graph(row) for row in events_for_linking(client, *window))
                    if pair[0] not in redone]
    links = link_events(results, link_config, existing=existing)
    write(PipelineOutput(results=results, links=links))
    report.links = len(links)
    report.orphans_removed = sum(int(row["removed"]) for row in client.run(_DELETE_ORPHANS))
    report.applied = True
    log.info("re-extraction applied", extra={"fields": {
        "articles": len(results), "events_removed": report.events_removed, "events_added": report.events_added,
        "links": report.links, "orphans_removed": report.orphans_removed}})
    return report
