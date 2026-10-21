"""Stable query contract for the Graph DB & Backend lane.

These functions are the fallback target for Person C's RMI and the data source
for the FastAPI layer. They return plain Python dictionaries, never driver
objects. Names, parameters, and return shapes are stable; changing them
requires review from the consuming lane (ADR-0004).

Entity matching is exact and case-sensitive after Person A-compatible
normalization, so the ``entity_name`` index stays usable. A case-insensitive
fallback exists only for an empty exact match and is explicitly non-indexed.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from graphdb.connection import Neo4jClient
from graphdb.normalize import normalize_entity_name

EPOCH = dt.date(1970, 1, 1)
MAX_CHAIN_DEPTH = 5
DEFAULT_LIMIT = 100
MAX_LIMIT = 1000

# These Cypher strings contain no user data. The depth cap is a code constant;
# the user's depth is an integer parameter filtered with length(path).
_ENTITY_EXACT = """
MATCH (n:Entity {name: $name})
RETURN n.id AS id, n.name AS name, n.type AS type
ORDER BY n.id
LIMIT 2
"""

# Deliberately a non-indexed fallback. It runs only when the exact lookup
# returns nothing, and callers see match_mode="case_insensitive_scan".
_ENTITY_SCAN = """
MATCH (n:Entity)
WHERE toLower(n.name) = toLower($name)
RETURN n.id AS id, n.name AS name, n.type AS type
ORDER BY n.id
LIMIT 2
"""

_SEEDS_BY_ENTITY_ID = """
MATCH (seed:Event)-[:INVOLVES]->(n:Entity {id: $entity_id})
RETURN DISTINCT seed.id AS id
"""

_SEEDS_BY_TOPIC = """
MATCH (seed:Event)-[:ABOUT]->(t:Topic {name: $topic})
RETURN DISTINCT seed.id AS id
"""

_SEEDS_BY_DATE_RANGE = """
MATCH (seed:Event)
WHERE seed.date >= date($start) AND seed.date <= date($end)
RETURN DISTINCT seed.id AS id
"""

_PATHS_FROM_SEEDS = f"""
UNWIND $seed_ids AS seed_id
MATCH (seed:Event {{id: seed_id}})
MATCH path = (seed)-[:LINKED_TO*1..{MAX_CHAIN_DEPTH}]->(other:Event)
WHERE length(path) <= $depth
  AND all(rel IN relationships(path) WHERE rel.confidence >= $min_confidence)
RETURN [node IN nodes(path) | node.id] AS event_ids,
       [rel IN relationships(path) | {{
            from_id: startNode(rel).id,
            to_id: endNode(rel).id,
            confidence: rel.confidence,
            reason: rel.reason
       }}] AS links
"""

_EVENTS_BY_IDS = """
UNWIND $ids AS id
MATCH (e:Event {id: id})
OPTIONAL MATCH (a:Article)-[:DESCRIBES]->(e)
OPTIONAL MATCH (e)-[:INVOLVES]->(n:Entity)
OPTIONAL MATCH (e)-[:ABOUT]->(t:Topic)
RETURN e.id AS id, e.description AS description, e.date AS date, e.type AS type,
       e.date_source AS date_source,
       collect(DISTINCT a.id) AS article_ids,
       collect(DISTINCT {id: n.id, name: n.name, type: n.type}) AS entities,
       collect(DISTINCT t.name) AS topics
ORDER BY e.date, e.id
"""

_EVENT_BY_ID = """
MATCH (e:Event {id: $id})
OPTIONAL MATCH (a:Article)-[:DESCRIBES]->(e)
OPTIONAL MATCH (e)-[:INVOLVES]->(n:Entity)
OPTIONAL MATCH (e)-[:ABOUT]->(t:Topic)
RETURN e.id AS id, e.description AS description, e.date AS date, e.type AS type,
       e.date_source AS date_source,
       collect(DISTINCT a.id) AS article_ids,
       collect(DISTINCT {id: n.id, name: n.name, type: n.type}) AS entities,
       collect(DISTINCT t.name) AS topics
"""

_EVENTS_IN_DATE_RANGE = """
MATCH (e:Event)
WHERE e.date >= date($start) AND e.date <= date($end)
OPTIONAL MATCH (a:Article)-[:DESCRIBES]->(e)
OPTIONAL MATCH (e)-[:INVOLVES]->(n:Entity)
OPTIONAL MATCH (e)-[:ABOUT]->(t:Topic)
RETURN e.id AS id, e.description AS description, e.date AS date, e.type AS type,
       e.date_source AS date_source,
       collect(DISTINCT a.id) AS article_ids,
       collect(DISTINCT {id: n.id, name: n.name, type: n.type}) AS entities,
       collect(DISTINCT t.name) AS topics
ORDER BY e.date, e.id
SKIP $offset LIMIT $limit
"""

# Kept in sync with the query above, but without the OPTIONAL MATCH fan-out.
# Used by the integration index-evidence test.
_EVENTS_IN_DATE_RANGE_EXPLAIN = """
MATCH (e:Event)
WHERE e.date >= date($start) AND e.date <= date($end)
RETURN e.id AS id
ORDER BY e.date, e.id
"""


def date_key(value: dt.date | str) -> int:
    """Days since 1970-01-01, matching ``pipeline/export.py``."""

    day = dt.date.fromisoformat(value) if isinstance(value, str) else value
    return (day - EPOCH).days


def _iso_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return value.isoformat()
    if hasattr(value, "iso_format"):
        return value.iso_format()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    text = str(value)
    return text[:10] if len(text) >= 10 else text


def _coerce_date(value: dt.date | str, name: str) -> str:
    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value).isoformat()
        except ValueError as exc:
            raise ValueError(f"{name} must be a date or ISO date string") from exc
    raise ValueError(f"{name} must be a date or ISO date string")


def _coerce_limit(limit: int) -> int:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise ValueError("limit must be a positive integer")
    return min(limit, MAX_LIMIT)


def _coerce_offset(offset: int) -> int:
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ValueError("offset must be a non-negative integer")
    return offset


def _coerce_confidence(min_confidence: float) -> float:
    try:
        value = float(min_confidence)
    except (TypeError, ValueError) as exc:
        raise ValueError("min_confidence must be a number between 0.0 and 1.0") from exc
    if not 0.0 <= value <= 1.0:
        raise ValueError("min_confidence must be between 0.0 and 1.0")
    return value


def _coerce_depth(depth: int) -> int:
    if not isinstance(depth, int) or isinstance(depth, bool) or depth <= 0:
        raise ValueError("depth must be a positive integer")
    return min(depth, MAX_CHAIN_DEPTH)


def _entity_row(row: dict[str, Any]) -> dict[str, Any]:
    return {"id": row.get("id"), "name": row.get("name"), "type": row.get("type")}


def _event_row(row: dict[str, Any]) -> dict[str, Any]:
    date_text = _iso_date(row.get("date"))
    article_ids = [value for value in (row.get("article_ids") or []) if value]
    entities = [
        {"id": entity.get("id"), "name": entity.get("name"), "type": entity.get("type")}
        for entity in (row.get("entities") or [])
        if entity and entity.get("id")
    ]
    topics = sorted(value for value in (row.get("topics") or []) if value)
    return {
        "id": row.get("id"),
        "description": row.get("description"),
        "date": date_text,
        "date_key": date_key(date_text) if date_text else None,
        "type": row.get("type"),
        "date_source": row.get("date_source"),
        "article_id": article_ids[0] if article_ids else None,
        "entities": sorted(entities, key=lambda item: (item["name"] or "", item["id"] or "")),
        "topics": topics,
    }


def _sorted_events(events: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(events.values(), key=lambda row: (row.get("date") or "", row.get("id") or ""))


def _link_rows(
    links: dict[tuple[str, str], dict[str, Any]],
    events: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for (from_id, to_id), link in links.items():
        from_event = events.get(from_id, {})
        to_event = events.get(to_id, {})
        rows.append(
            {
                "from_event_id": from_id,
                "to_event_id": to_id,
                "confidence": float(link.get("confidence") or 0.0),
                "reason": link.get("reason") or "",
                "from_date": from_event.get("date"),
                "to_date": to_event.get("date"),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row.get("from_date") or "",
            row.get("from_event_id") or "",
            row.get("to_date") or "",
            row.get("to_event_id") or "",
        ),
    )


def find_entity(client: Neo4jClient, name: str) -> tuple[dict[str, Any] | None, str, bool]:
    """Find an entity by normalized exact name.

    Returns ``(entity_or_none, match_mode, ambiguous)``. ``match_mode`` is
    ``"exact"``, ``"case_insensitive_scan"``, or ``"none"``.
    """

    normalized = normalize_entity_name(name)
    rows = client.run(_ENTITY_EXACT, {"name": normalized})
    if rows:
        return _entity_row(rows[0]), "exact", len(rows) > 1

    rows = client.run(_ENTITY_SCAN, {"name": normalized})
    if rows:
        return _entity_row(rows[0]), "case_insensitive_scan", len(rows) > 1

    return None, "none", False


def _seed_ids(client: Neo4jClient, query: str, parameters: dict[str, Any]) -> set[str]:
    return {str(row["id"]) for row in client.run(query, parameters) if row.get("id")}


def _fetch_events(client: Neo4jClient, event_ids: set[str]) -> dict[str, dict[str, Any]]:
    if not event_ids:
        return {}
    rows = client.run(_EVENTS_BY_IDS, {"ids": sorted(event_ids)})
    return {str(row["id"]): _event_row(row) for row in rows if row.get("id")}


def _collect_paths(
    client: Neo4jClient,
    seed_ids: set[str],
    min_confidence: float,
    depth: int,
) -> tuple[set[str], dict[tuple[str, str], dict[str, Any]]]:
    if not seed_ids:
        return set(), {}

    rows = client.run(
        _PATHS_FROM_SEEDS,
        {
            "seed_ids": sorted(seed_ids),
            "depth": depth,
            "min_confidence": min_confidence,
        },
    )
    event_ids = set(seed_ids)
    links: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        event_ids.update(str(value) for value in (row.get("event_ids") or []) if value)
        for link in row.get("links") or []:
            if not link:
                continue
            key = (str(link.get("from_id")), str(link.get("to_id")))
            previous = links.get(key)
            if previous is None or float(link.get("confidence") or 0.0) > float(
                previous.get("confidence") or 0.0
            ):
                links[key] = link
    return event_ids, links


def _chain_payload(
    client: Neo4jClient,
    seed_ids: set[str],
    min_confidence: float,
    depth: int,
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    event_ids, link_map = _collect_paths(client, seed_ids, min_confidence, depth)
    events = _fetch_events(client, event_ids)
    ordered = _sorted_events(events)
    truncated = len(ordered) > limit
    selected = ordered[:limit]
    selected_ids = {row["id"] for row in selected}
    selected_links = {
        key: value for key, value in link_map.items() if key[0] in selected_ids and key[1] in selected_ids
    }
    return selected, _link_rows(selected_links, events), truncated


def event_by_id(client: Neo4jClient, event_id: str) -> dict[str, Any] | None:
    """Return one event with its article, entities, and topics, or ``None``."""

    if not isinstance(event_id, str) or not event_id.strip():
        raise ValueError("event_id must be a non-empty string")
    rows = client.run(_EVENT_BY_ID, {"id": event_id})
    return _event_row(rows[0]) if rows else None


def events_in_date_range(
    client: Neo4jClient,
    start: dt.date | str,
    end: dt.date | str,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return events whose native date is in the inclusive range.

    This is the primary RMI fallback target and is intended to use the
    ``event_date`` range index.
    """

    start_text = _coerce_date(start, "start")
    end_text = _coerce_date(end, "end")
    if start_text > end_text:
        raise ValueError("start must be on or before end")
    rows = client.run(
        _EVENTS_IN_DATE_RANGE,
        {
            "start": start_text,
            "end": end_text,
            "limit": _coerce_limit(limit),
            "offset": _coerce_offset(offset),
        },
    )
    return [_event_row(row) for row in rows]


def chain_by_entity(
    client: Neo4jClient,
    name: str,
    min_confidence: float = 0.0,
    depth: int = 3,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Return events reachable from an entity's events via ``LINKED_TO``."""

    normalized = normalize_entity_name(name)
    min_confidence_value = _coerce_confidence(min_confidence)
    depth_value = _coerce_depth(depth)
    limit_value = _coerce_limit(limit)
    entity, match_mode, ambiguous = find_entity(client, name)
    base = {
        "query": {
            "entity_name": name,
            "normalized_name": normalized,
            "min_confidence": min_confidence_value,
            "depth": depth_value,
            "limit": limit_value,
        },
        "entity": entity,
        "match_mode": match_mode,
        "ambiguous": ambiguous,
    }
    if entity is None:
        base.update({"events": [], "links": [], "truncated": False})
        return base

    seed_ids = _seed_ids(client, _SEEDS_BY_ENTITY_ID, {"entity_id": entity["id"]})
    events, links, truncated = _chain_payload(
        client, seed_ids, base["query"]["min_confidence"], base["query"]["depth"], base["query"]["limit"]
    )
    base.update({"events": events, "links": links, "truncated": truncated})
    return base


def chain_by_topic(
    client: Neo4jClient,
    topic: str,
    min_confidence: float = 0.0,
    depth: int = 3,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Return events reachable from events about a topic via ``LINKED_TO``."""

    if not isinstance(topic, str) or not topic.strip():
        raise ValueError("topic must be a non-empty string")
    min_confidence_value = _coerce_confidence(min_confidence)
    depth_value = _coerce_depth(depth)
    limit_value = _coerce_limit(limit)
    seed_ids = _seed_ids(client, _SEEDS_BY_TOPIC, {"topic": topic})
    events, links, truncated = _chain_payload(
        client, seed_ids, min_confidence_value, depth_value, limit_value
    )
    return {
        "query": {
            "topic": topic,
            "min_confidence": min_confidence_value,
            "depth": depth_value,
            "limit": limit_value,
        },
        "match_mode": "exact" if seed_ids else "none",
        "events": events,
        "links": links,
        "truncated": truncated,
    }


def chain_by_date_range(
    client: Neo4jClient,
    start: dt.date | str,
    end: dt.date | str,
    min_confidence: float = 0.0,
    depth: int = 3,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Return chains seeded by events inside an inclusive date range."""

    start_text = _coerce_date(start, "start")
    end_text = _coerce_date(end, "end")
    if start_text > end_text:
        raise ValueError("start must be on or before end")
    min_confidence_value = _coerce_confidence(min_confidence)
    depth_value = _coerce_depth(depth)
    limit_value = _coerce_limit(limit)
    seed_ids = _seed_ids(client, _SEEDS_BY_DATE_RANGE, {"start": start_text, "end": end_text})
    events, links, truncated = _chain_payload(
        client, seed_ids, min_confidence_value, depth_value, limit_value
    )
    return {
        "query": {
            "start": start_text,
            "end": end_text,
            "min_confidence": min_confidence_value,
            "depth": depth_value,
            "limit": limit_value,
        },
        "match_mode": "exact" if seed_ids else "none",
        "events": events,
        "links": links,
        "truncated": truncated,
    }


def explain_events_in_date_range(
    client: Neo4jClient,
    start: dt.date | str,
    end: dt.date | str,
) -> dict[str, Any]:
    """Return the EXPLAIN plan for the date-range lookup.

    Used by the integration index-evidence test. The plan is a nested plain
    dictionary; callers should stringify it before asserting on index names.
    """

    start_text = _coerce_date(start, "start")
    end_text = _coerce_date(end, "end")
    return client.explain(
        "EXPLAIN " + _EVENTS_IN_DATE_RANGE_EXPLAIN,
        {"start": start_text, "end": end_text},
    )


_EVENTS_FOR_LINKING = """
MATCH (a:Article)-[:DESCRIBES]->(e:Event)
WHERE e.date >= date($start) AND e.date <= date($end)
OPTIONAL MATCH (e)-[:INVOLVES]->(n:Entity)
OPTIONAL MATCH (e)-[:ABOUT]->(t:Topic)
WITH e, min(a.id) AS article_id,
     [x IN collect(DISTINCT {id: n.id, name: n.name, type: n.type}) WHERE x.id IS NOT NULL] AS entities,
     head(collect(DISTINCT t.name)) AS topic
RETURN e.id AS id, e.description AS description, e.date AS date, e.type AS type,
       coalesce(e.date_source, 'explicit') AS date_source, coalesce(e.source_text, '') AS source_text,
       article_id, entities, coalesce(topic, 'general') AS topic
ORDER BY e.date, e.id
LIMIT $limit
"""

_EXISTING_ARTICLE_IDS = "UNWIND $ids AS id MATCH (a:Article {id: id}) RETURN a.id AS id"

_LATEST_ARTICLE_DATE = "MATCH (a:Article) RETURN max(a.date) AS latest"


def events_for_linking(
    client: Neo4jClient,
    start: dt.date | str,
    end: dt.date | str,
    limit: int = 20000,
) -> list[dict[str, Any]]:
    """Events in a date window with everything the pipeline's linker scores on.

    Used by incremental ingestion to link new events to ones already in the graph.
    ``limit`` is a safety cap, not pagination; callers should keep windows bounded.
    """

    rows = client.run(
        _EVENTS_FOR_LINKING,
        {"start": _coerce_date(start, "start"), "end": _coerce_date(end, "end"), "limit": int(limit)},
    )
    for row in rows:
        row["date"] = _iso_date(row["date"])
    return rows


def existing_article_ids(client: Neo4jClient, ids: list[str]) -> set[str]:
    if not ids:
        return set()
    return {str(row["id"]) for row in client.run(_EXISTING_ARTICLE_IDS, {"ids": sorted(set(ids))})}


def latest_article_date(client: Neo4jClient) -> dt.date | None:
    rows = client.run(_LATEST_ARTICLE_DATE)
    latest = _iso_date(rows[0]["latest"]) if rows else None
    return dt.date.fromisoformat(latest) if latest else None
