"""Incremental ingestion: fetch new articles, extract, link against the graph, write.

One run:
1. Works out the fetch window: from the newest Article already in the graph (minus an overlap,
   because Guardian publication dates are days, not timestamps) to today. An empty graph starts
   ``initial_days`` back.
2. Fetches every configured query and drops articles already in the graph.
3. Extracts events from the new articles only.
4. Loads graph events within ``lookback_days`` of the new events' dates and links new events
   against them and each other (never existing<->existing; an earlier run did those).
5. Writes the batch (idempotent MERGE) unless ``dry_run``, then exports the graph's event keys.

Everything external (article sources, Neo4j client, writer) is injected so it can be tested offline.
"""

import datetime
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from common.schema import Entity, Event, ExtractedEvent, PipelineOutput, Topic
from pipeline.config import LinkConfig
from pipeline.export import write_pipeline_json
from pipeline.extract import Extractor
from pipeline.ingest import ArticleSource, RawArticle
from pipeline.link import link_events

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestQuery:
    query : str
    section : str | None = None


@dataclass(frozen=True)
class IngestConfig:
    queries : tuple[IngestQuery, ...]
    max_per_query : int = 20
    initial_days : int = 30     # fetch window for an empty graph
    overlap_days : int = 2      # re-fetch this many days before the newest stored article
    lookback_days : int = 90    # how far back new events look for existing events to link to


@dataclass
class IngestSummary:
    from_date : str
    to_date : str
    fetched : int = 0
    new_articles : int = 0
    events : int = 0
    existing_events_considered : int = 0
    links : int = 0
    links_to_existing : int = 0
    written : bool = False
    write_counts : dict = field(default_factory=dict)


def load_ingest_config(path: str | Path) -> IngestConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    queries = tuple(IngestQuery(q["query"], q.get("section")) for q in data["queries"])
    if not queries:
        raise ValueError(f"{path}: at least one query is required")
    return IngestConfig(
        queries=queries,
        max_per_query=int(data.get("max_per_query", 20)),
        initial_days=int(data.get("initial_days", 30)),
        overlap_days=int(data.get("overlap_days", 2)),
        lookback_days=int(data.get("lookback_days", 90)),
    )


def fetch_window(latest: datetime.date | None, today: datetime.date, config: IngestConfig) -> tuple[datetime.date, datetime.date]:
    start = latest - datetime.timedelta(days=config.overlap_days) if latest else today - datetime.timedelta(days=config.initial_days)
    return min(start, today), today


def extracted_from_graph(row: dict) -> tuple[str, ExtractedEvent]:
    event = Event(id=row["id"], description=row["description"], date=datetime.date.fromisoformat(row["date"]),
                  type=row["type"], date_source=row["date_source"])
    entities = [Entity(id=e["id"], name=e["name"], type=e["type"]) for e in row["entities"]]
    return row["article_id"], ExtractedEvent(event=event, entities=entities, topic=Topic(name=row["topic"]),
                                             source_text=row["source_text"])


def run_ingest(
    config: IngestConfig,
    make_source: Callable[[IngestQuery, datetime.date, datetime.date], ArticleSource],
    extractor: Extractor,
    client,
    write: Callable[[PipelineOutput], object] | None,
    link_config: LinkConfig = LinkConfig(),
    today: datetime.date | None = None,
    out_dir: Path | None = None,
) -> IngestSummary:
    # Imported here so the pipeline package itself does not require the Neo4j driver.
    from graphdb.queries import events_for_linking, existing_article_ids, latest_article_date

    today = today or datetime.date.today()
    start, end = fetch_window(latest_article_date(client), today, config)
    summary = IngestSummary(from_date=start.isoformat(), to_date=end.isoformat())
    log.info("ingest window", extra={"fields": {"from": summary.from_date, "to": summary.to_date, "queries": len(config.queries)}})

    by_id: dict[str, RawArticle] = {}
    for query in config.queries:
        for raw in make_source(query, start, end).load():
            by_id.setdefault(raw.article.id, raw)
    summary.fetched = len(by_id)

    known = existing_article_ids(client, list(by_id))
    new = sorted((r for i, r in by_id.items() if i not in known), key=lambda r: (r.article.date, r.article.id))
    summary.new_articles = len(new)
    if not new:
        log.info("no new articles", extra={"fields": {"fetched": summary.fetched}})
        return summary

    results = [extractor.extract(raw.article, raw.text) for raw in new]
    new_events = [e for r in results for e in r.events]
    summary.events = len(new_events)
    if not new_events:
        log.info("new articles produced no events", extra={"fields": {"new_articles": summary.new_articles}})

    existing = []
    if new_events:
        dates = [e.event.date for e in new_events]
        window_start = min(dates) - datetime.timedelta(days=config.lookback_days)
        existing = [extracted_from_graph(row) for row in events_for_linking(client, window_start, max(dates))]
    summary.existing_events_considered = len(existing)

    links = link_events(results, link_config, existing=existing)
    new_ids = {e.event.id for e in new_events}
    summary.links = len(links)
    summary.links_to_existing = sum(1 for lk in links if lk.from_event_id not in new_ids or lk.to_event_id not in new_ids)

    output = PipelineOutput(results=results, links=links)
    if out_dir is not None:
        write_pipeline_json(output, Path(out_dir) / "ingest_batch.json")
    if write is not None:
        result = write(output)
        summary.written = True
        summary.write_counts = dict(vars(getattr(result, "counts", result))) if result is not None else {}
    log.info("ingest done", extra={"fields": {k: v for k, v in vars(summary).items() if k != "write_counts"}})
    return summary
