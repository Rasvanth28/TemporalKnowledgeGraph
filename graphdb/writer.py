"""Idempotent, parameterized writer from pipeline output into Neo4j.

The writer accepts either ``common.schema.PipelineOutput`` objects or the JSON
shape produced by ``pipeline.export.write_pipeline_json``.

Key semantics, recorded in ADR-0002 and ADR-0003:

- ``MERGE`` on stable ids: Article.id, Event.id, Entity.id, Topic.name.
- Native Neo4j dates via ``date($param)``.
- ``LINKED_TO`` is latest-input-wins.
- Link endpoints are validated against the batch and the existing graph before
  any write; a missing endpoint fails the batch with a clear error.
- ``PRECEDES`` is a global ``(date, id)`` chain rebuilt in one transaction after
  each batch.
- Created vs matched node/relationship counts use a temporary batch marker that
  is removed inside the same transaction.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping
import uuid

from common.schema import (
    Article,
    Entity,
    Event,
    EventLink,
    ExtractedEvent,
    ExtractionResult,
    PipelineOutput,
    Topic,
)
from graphdb.config import ConfigurationError, load_neo4j_config
from graphdb.connection import Neo4jClient

_MARKER = "_person_b_batch"

_ARTICLE_COLUMNS = ("id", "title", "date", "source", "url")
_EVENT_COLUMNS = ("id", "description", "date", "type", "date_source")
_ENTITY_COLUMNS = ("id", "name", "type")


class WriterValidationError(ValueError):
    """Raised when pipeline output cannot be written safely."""


@dataclass(frozen=True)
class WritePlan:
    articles: tuple[dict[str, Any], ...]
    events: tuple[dict[str, Any], ...]
    entities: tuple[dict[str, Any], ...]
    topics: tuple[dict[str, Any], ...]
    describes: tuple[dict[str, str], ...]
    mentions: tuple[dict[str, str], ...]
    involves: tuple[dict[str, str], ...]
    event_about: tuple[dict[str, str], ...]
    article_about: tuple[dict[str, str], ...]
    linked_to: tuple[dict[str, Any], ...]
    event_ids: frozenset[str]
    link_endpoint_ids: frozenset[str]

    @property
    def node_count(self) -> int:
        return len(self.articles) + len(self.events) + len(self.entities) + len(self.topics)

    @property
    def relationship_count(self) -> int:
        return (
            len(self.describes)
            + len(self.mentions)
            + len(self.involves)
            + len(self.event_about)
            + len(self.article_about)
            + len(self.linked_to)
        )


@dataclass(frozen=True)
class WriteCounts:
    articles: int
    events: int
    entities: int
    topics: int
    describes: int
    mentions: int
    involves: int
    event_about: int
    article_about: int
    linked_to: int
    nodes_created: int
    nodes_matched: int
    relationships_created: int
    relationships_matched: int
    precedes_rebuilt: int

    def as_dict(self) -> dict[str, int]:
        return {
            "articles": self.articles,
            "events": self.events,
            "entities": self.entities,
            "topics": self.topics,
            "describes": self.describes,
            "mentions": self.mentions,
            "involves": self.involves,
            "event_about": self.event_about,
            "article_about": self.article_about,
            "linked_to": self.linked_to,
            "nodes_created": self.nodes_created,
            "nodes_matched": self.nodes_matched,
            "relationships_created": self.relationships_created,
            "relationships_matched": self.relationships_matched,
            "precedes_rebuilt": self.precedes_rebuilt,
        }


@dataclass(frozen=True)
class WriteResult:
    batch_id: str
    counts: WriteCounts

    def as_dict(self) -> dict[str, Any]:
        return {"batch_id": self.batch_id, "counts": self.counts.as_dict()}


# ---------------------------------------------------------------------------
# JSON/dataclass parsing
# ---------------------------------------------------------------------------


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WriterValidationError(f"{path} must be an object")
    return value


def _text(mapping: Mapping[str, Any], key: str, path: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise WriterValidationError(f"{path}.{key} must be a non-empty string")
    return value


def _optional_text(mapping: Mapping[str, Any], key: str, default: str = "") -> str:
    value = mapping.get(key, default)
    return value if isinstance(value, str) else default


def _items(value: Any, path: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise WriterValidationError(f"{path} must be a list")
    return value


def _date(value: Any, path: str) -> dt.date:
    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value)
        except ValueError as exc:
            raise WriterValidationError(f"{path} is not an ISO date: {value!r}") from exc
    raise WriterValidationError(f"{path} must be a date or ISO date string")


def _entity(mapping: Mapping[str, Any], path: str) -> Entity:
    return Entity(
        id=_text(mapping, "id", path),
        name=_text(mapping, "name", path),
        type=_text(mapping, "type", path),
    )


def _event(mapping: Mapping[str, Any], path: str) -> Event:
    return Event(
        id=_text(mapping, "id", path),
        description=_text(mapping, "description", path),
        date=_date(mapping.get("date"), f"{path}.date"),
        type=_text(mapping, "type", path),
        date_source=str(mapping.get("date_source") or "explicit"),
    )


def _event_link(mapping: Mapping[str, Any], path: str) -> EventLink:
    confidence = mapping.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        raise WriterValidationError(f"{path}.confidence must be a number")
    confidence = float(confidence)
    if not 0.0 <= confidence <= 1.0:
        raise WriterValidationError(f"{path}.confidence must be between 0.0 and 1.0")
    return EventLink(
        from_event_id=_text(mapping, "from_event_id", path),
        to_event_id=_text(mapping, "to_event_id", path),
        confidence=confidence,
        reason=_text(mapping, "reason", path),
    )


def pipeline_output_from_mapping(data: Mapping[str, Any]) -> PipelineOutput:
    """Parse the JSON shape from ``pipeline/export.py`` into dataclasses."""

    results: list[ExtractionResult] = []
    for index, raw_result in enumerate(_items(data.get("results"), "results")):
        path = f"results[{index}]"
        result = _mapping(raw_result, path)
        article_data = _mapping(result.get("article"), f"{path}.article")
        article = Article(
            id=_text(article_data, "id", f"{path}.article"),
            title=_text(article_data, "title", f"{path}.article"),
            date=_date(article_data.get("date"), f"{path}.article.date"),
            source=_optional_text(article_data, "source"),
            url=_optional_text(article_data, "url"),
        )
        entities = [
            _entity(_mapping(item, f"{path}.entities[{i}]"), f"{path}.entities[{i}]")
            for i, item in enumerate(_items(result.get("entities"), f"{path}.entities"))
        ]
        events: list[ExtractedEvent] = []
        for event_index, raw_event in enumerate(_items(result.get("events"), f"{path}.events")):
            event_path = f"{path}.events[{event_index}]"
            event_data = _mapping(raw_event, event_path)
            topic_data = _mapping(event_data.get("topic"), f"{event_path}.topic")
            events.append(
                ExtractedEvent(
                    event=_event(_mapping(event_data.get("event"), f"{event_path}.event"), f"{event_path}.event"),
                    entities=[
                        _entity(_mapping(item, f"{event_path}.entities[{i}]"), f"{event_path}.entities[{i}]")
                        for i, item in enumerate(_items(event_data.get("entities"), f"{event_path}.entities"))
                    ],
                    topic=Topic(name=_text(topic_data, "name", f"{event_path}.topic")),
                    source_text=_optional_text(event_data, "source_text"),
                )
            )
        results.append(ExtractionResult(article=article, entities=entities, events=events))

    links = [
        _event_link(_mapping(item, f"links[{i}]"), f"links[{i}]")
        for i, item in enumerate(_items(data.get("links"), "links"))
    ]
    return PipelineOutput(results=results, links=links)


def load_pipeline_output(path: str | Path) -> PipelineOutput:
    with open(path, encoding="utf-8") as file:
        data = json.load(file)
    return pipeline_output_from_mapping(_mapping(data, "pipeline_output"))


# ---------------------------------------------------------------------------
# Planning/validation
# ---------------------------------------------------------------------------


def _add_unique(store: dict[str, dict[str, Any]], row: dict[str, Any], key: str, path: str) -> None:
    existing = store.get(row[key])
    if existing is not None:
        raise WriterValidationError(f"duplicate {path} id/name in payload: {row[key]!r}")
    store[row[key]] = row


def _add_entity(store: dict[str, dict[str, Any]], row: dict[str, Any]) -> None:
    # Entity ids repeat across articles by design. Keep the first observed
    # spelling for a stable graph name; a same-id/type row has the same entity.
    store.setdefault(row["id"], row)


def build_write_plan(output: PipelineOutput) -> WritePlan:
    """Convert validated pipeline output into parameter-ready rows."""

    articles: dict[str, dict[str, Any]] = {}
    events: dict[str, dict[str, Any]] = {}
    entities: dict[str, dict[str, Any]] = {}
    topics: dict[str, dict[str, Any]] = {}
    describes: set[tuple[str, str]] = set()
    mentions: set[tuple[str, str]] = set()
    involves: set[tuple[str, str]] = set()
    event_about: set[tuple[str, str]] = set()
    article_about: dict[str, set[str]] = {}
    link_candidates: dict[tuple[str, str], EventLink] = {}

    for result in output.results:
        article = result.article
        if not article.id:
            raise WriterValidationError("article id must be non-empty")
        _add_unique(
            articles,
            {
                "id": article.id,
                "title": article.title,
                "date": article.date.isoformat(),
                "source": article.source,
                "url": article.url,
            },
            "id",
            "Article",
        )

        article_mention_ids: set[str] = set()
        for entity in result.entities:
            _add_entity(entities, {"id": entity.id, "name": entity.name, "type": entity.type})
            article_mention_ids.add(entity.id)
            mentions.add((article.id, entity.id))

        article_topics = article_about.setdefault(article.id, set())
        for extracted in result.events:
            event = extracted.event
            _add_unique(
                events,
                {
                    "id": event.id,
                    "description": event.description,
                    "date": event.date.isoformat(),
                    "type": event.type,
                    "date_source": event.date_source,
                },
                "id",
                "Event",
            )
            describes.add((article.id, event.id))

            for entity in extracted.entities:
                if entity.id not in article_mention_ids:
                    raise WriterValidationError(
                        f"event {event.id!r} references entity {entity.id!r} "
                        f"that the article does not mention"
                    )
                _add_entity(entities, {"id": entity.id, "name": entity.name, "type": entity.type})
                involves.add((event.id, entity.id))

            topic_name = extracted.topic.name
            topics.setdefault(topic_name, {"name": topic_name})
            event_about.add((event.id, topic_name))
            article_topics.add(topic_name)

    for link in output.links:
        if link.from_event_id == link.to_event_id:
            raise WriterValidationError(f"LINKED_TO self-link is not allowed: {link.from_event_id!r}")
        key = (link.from_event_id, link.to_event_id)
        previous = link_candidates.get(key)
        if previous is None or (link.confidence, link.reason) > (previous.confidence, previous.reason):
            link_candidates[key] = link

    article_about_rows = [
        {"article_id": article_id, "topic_name": topic_name}
        for article_id, topic_names in sorted(article_about.items())
        for topic_name in sorted(topic_names)
    ]

    linked_to_rows = [
        {
            "from_event_id": link.from_event_id,
            "to_event_id": link.to_event_id,
            "confidence": link.confidence,
            "reason": link.reason,
        }
        for _, link in sorted(link_candidates.items())
    ]

    event_ids = frozenset(events)
    link_endpoint_ids = frozenset(
        {row["from_event_id"] for row in linked_to_rows} | {row["to_event_id"] for row in linked_to_rows}
    )

    return WritePlan(
        articles=tuple(articles.values()),
        events=tuple(events.values()),
        entities=tuple(entities.values()),
        topics=tuple(topics.values()),
        describes=tuple({"article_id": a, "event_id": e} for a, e in sorted(describes)),
        mentions=tuple({"article_id": a, "entity_id": e} for a, e in sorted(mentions)),
        involves=tuple({"event_id": e, "entity_id": n} for e, n in sorted(involves)),
        event_about=tuple({"event_id": e, "topic_name": t} for e, t in sorted(event_about)),
        article_about=tuple(article_about_rows),
        linked_to=tuple(linked_to_rows),
        event_ids=event_ids,
        link_endpoint_ids=link_endpoint_ids,
    )


# ---------------------------------------------------------------------------
# Cypher
# ---------------------------------------------------------------------------

_WRITE_ARTICLES = """
UNWIND $rows AS row
MERGE (a:Article {id: row.id})
ON CREATE SET a.title = row.title, a.date = date(row.date), a.source = row.source,
              a.url = row.url, a._person_b_batch = $batch
ON MATCH SET a.title = row.title, a.date = date(row.date), a.source = row.source, a.url = row.url
"""

_WRITE_EVENTS = """
UNWIND $rows AS row
MERGE (e:Event {id: row.id})
ON CREATE SET e.description = row.description, e.date = date(row.date), e.type = row.type,
              e.date_source = row.date_source, e._person_b_batch = $batch
ON MATCH SET e.description = row.description, e.date = date(row.date), e.type = row.type,
             e.date_source = row.date_source
"""

_WRITE_ENTITIES = """
UNWIND $rows AS row
MERGE (n:Entity {id: row.id})
ON CREATE SET n.name = row.name, n.type = row.type, n._person_b_batch = $batch
ON MATCH SET n.name = row.name, n.type = row.type
"""

_WRITE_TOPICS = """
UNWIND $rows AS row
MERGE (t:Topic {name: row.name})
ON CREATE SET t._person_b_batch = $batch
"""

_WRITE_DESCRIBES = """
UNWIND $rows AS row
MATCH (a:Article {id: row.article_id}), (e:Event {id: row.event_id})
MERGE (a)-[r:DESCRIBES]->(e)
ON CREATE SET r._person_b_batch = $batch
"""

_WRITE_MENTIONS = """
UNWIND $rows AS row
MATCH (a:Article {id: row.article_id}), (n:Entity {id: row.entity_id})
MERGE (a)-[r:MENTIONS]->(n)
ON CREATE SET r._person_b_batch = $batch
"""

_WRITE_INVOLVES = """
UNWIND $rows AS row
MATCH (e:Event {id: row.event_id}), (n:Entity {id: row.entity_id})
MERGE (e)-[r:INVOLVES]->(n)
ON CREATE SET r._person_b_batch = $batch
"""

_WRITE_EVENT_ABOUT = """
UNWIND $rows AS row
MATCH (e:Event {id: row.event_id}), (t:Topic {name: row.topic_name})
MERGE (e)-[r:ABOUT]->(t)
ON CREATE SET r._person_b_batch = $batch
"""

_WRITE_ARTICLE_ABOUT = """
UNWIND $rows AS row
MATCH (a:Article {id: row.article_id}), (t:Topic {name: row.topic_name})
MERGE (a)-[r:ABOUT]->(t)
ON CREATE SET r._person_b_batch = $batch
"""

_WRITE_LINKED_TO = """
UNWIND $rows AS row
MATCH (a:Event {id: row.from_event_id}), (b:Event {id: row.to_event_id})
MERGE (a)-[r:LINKED_TO]->(b)
ON CREATE SET r.confidence = row.confidence, r.reason = row.reason, r._person_b_batch = $batch
ON MATCH SET r.confidence = row.confidence, r.reason = row.reason
"""

_COUNT_CREATED_NODES = (
    "MATCH (n) WHERE n._person_b_batch = $batch RETURN count(n) AS created"
)
_CLEAR_NODE_MARKERS = (
    "MATCH (n) WHERE n._person_b_batch = $batch REMOVE n._person_b_batch"
)
_COUNT_CREATED_RELATIONSHIPS = (
    "MATCH ()-[r]->() WHERE r._person_b_batch = $batch RETURN count(r) AS created"
)
_CLEAR_RELATIONSHIP_MARKERS = (
    "MATCH ()-[r]->() WHERE r._person_b_batch = $batch REMOVE r._person_b_batch"
)

_DELETE_PRECEDES = "MATCH ()-[r:PRECEDES]->() DELETE r"

_REBUILD_PRECEDES = """
MATCH (e:Event)
WITH e ORDER BY e.date, e.id
WITH collect(e) AS events
WHERE size(events) > 1
UNWIND range(0, size(events) - 2) AS i
WITH events[i] AS a, events[i + 1] AS b
MERGE (a)-[:PRECEDES]->(b)
RETURN count(*) AS rebuilt
"""


def precedes_pairs(events: list[Mapping[str, Any]]) -> list[tuple[str, str]]:
    """Pure mirror of the Cypher PRECEDES ordering, used by unit tests."""

    ordered = sorted(events, key=lambda row: (str(row["date"]), str(row["id"])))
    return [(str(a["id"]), str(b["id"])) for a, b in zip(ordered, ordered[1:])]


def _run_rows(tx: Any, query: str, rows: tuple[dict[str, Any], ...], batch_id: str) -> None:
    if rows:
        tx.run(query, {"rows": list(rows), "batch": batch_id})


def _write_batch(tx: Any, plan: WritePlan, batch_id: str) -> WriteCounts:
    _run_rows(tx, _WRITE_ARTICLES, plan.articles, batch_id)
    _run_rows(tx, _WRITE_EVENTS, plan.events, batch_id)
    _run_rows(tx, _WRITE_ENTITIES, plan.entities, batch_id)
    _run_rows(tx, _WRITE_TOPICS, plan.topics, batch_id)

    _run_rows(tx, _WRITE_DESCRIBES, plan.describes, batch_id)
    _run_rows(tx, _WRITE_MENTIONS, plan.mentions, batch_id)
    _run_rows(tx, _WRITE_INVOLVES, plan.involves, batch_id)
    _run_rows(tx, _WRITE_EVENT_ABOUT, plan.event_about, batch_id)
    _run_rows(tx, _WRITE_ARTICLE_ABOUT, plan.article_about, batch_id)
    _run_rows(tx, _WRITE_LINKED_TO, plan.linked_to, batch_id)

    node_result = tx.run(_COUNT_CREATED_NODES, {"batch": batch_id})
    nodes_created = int(node_result.single()["created"])
    tx.run(_CLEAR_NODE_MARKERS, {"batch": batch_id})

    relationship_result = tx.run(_COUNT_CREATED_RELATIONSHIPS, {"batch": batch_id})
    relationships_created = int(relationship_result.single()["created"])
    tx.run(_CLEAR_RELATIONSHIP_MARKERS, {"batch": batch_id})

    return WriteCounts(
        articles=len(plan.articles),
        events=len(plan.events),
        entities=len(plan.entities),
        topics=len(plan.topics),
        describes=len(plan.describes),
        mentions=len(plan.mentions),
        involves=len(plan.involves),
        event_about=len(plan.event_about),
        article_about=len(plan.article_about),
        linked_to=len(plan.linked_to),
        nodes_created=nodes_created,
        nodes_matched=plan.node_count - nodes_created,
        relationships_created=relationships_created,
        relationships_matched=plan.relationship_count - relationships_created,
        precedes_rebuilt=0,
    )


def _rebuild_precedes(tx: Any) -> int:
    tx.run(_DELETE_PRECEDES)
    result = tx.run(_REBUILD_PRECEDES)
    record = result.single()
    return int(record["rebuilt"]) if record and record.get("rebuilt") is not None else 0


def graph_counts(client: Neo4jClient) -> dict[str, int]:
    """Return total node and relationship counts, used by idempotency tests."""

    nodes = client.run("MATCH (n) RETURN count(n) AS count")[0]["count"]
    relationships = client.run("MATCH ()-[r]->() RETURN count(r) AS count")[0]["count"]
    return {"nodes": int(nodes), "relationships": int(relationships)}


class PipelineWriter:
    """Write pipeline output into Neo4j, then rebuild the global PRECEDES chain."""

    def __init__(self, client: Neo4jClient):
        self.client = client

    def _ensure_link_endpoints(self, plan: WritePlan) -> None:
        candidates = set(plan.link_endpoint_ids) - set(plan.event_ids)
        if not candidates:
            return
        rows = self.client.run(
            "UNWIND $ids AS id MATCH (e:Event {id: id}) RETURN e.id AS id",
            {"ids": sorted(candidates)},
        )
        existing = {str(row["id"]) for row in rows}
        missing = candidates - existing
        if missing:
            raise WriterValidationError(
                "LINKED_TO endpoint(s) not found in the batch or the database: "
                + ", ".join(sorted(missing))
            )

    def write(self, output: PipelineOutput | Mapping[str, Any]) -> WriteResult:
        if isinstance(output, Mapping):
            output = pipeline_output_from_mapping(output)

        plan = build_write_plan(output)
        self._ensure_link_endpoints(plan)

        batch_id = uuid.uuid4().hex
        counts = self.client.execute_write(lambda tx: _write_batch(tx, plan, batch_id))
        precedes_rebuilt = self.client.execute_write(lambda tx: _rebuild_precedes(tx))
        return WriteResult(batch_id=batch_id, counts=replace(counts, precedes_rebuilt=precedes_rebuilt))


def write_pipeline_output(
    client: Neo4jClient,
    output: PipelineOutput | Mapping[str, Any],
) -> WriteResult:
    return PipelineWriter(client).write(output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write pipeline_output.json into Neo4j, idempotently."
    )
    parser.add_argument(
        "--input",
        default="data/exports/pipeline_output.json",
        help="Path to the pipeline JSON output (default: data/exports/pipeline_output.json).",
    )
    args = parser.parse_args(argv)

    try:
        output = load_pipeline_output(args.input)
    except (OSError, WriterValidationError) as exc:
        print(f"Writer input error: {type(exc).__name__}: {exc}")
        return 1

    try:
        config = load_neo4j_config()
    except ConfigurationError as exc:
        print(f"Writer configuration error: {exc}")
        return 1

    client = Neo4jClient(config)
    try:
        result = PipelineWriter(client).write(output)
    except WriterValidationError as exc:
        print(f"Writer validation failed: {exc}")
        return 1
    except Exception as exc:
        print(f"Writer failed: {type(exc).__name__}: {exc}")
        return 1
    finally:
        client.close()

    print(json.dumps(result.as_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
