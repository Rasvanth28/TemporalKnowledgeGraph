"""Keep the graph inside its plan: rolling-window retention and a size guard.

Aura Free stops at 200k nodes / 400k relationships. Ingesting everything (~170 Guardian articles a
day, ~20 nodes and ~53 relationships each) reaches that in about six weeks, so articles older than
the retention window are deleted together with their events, and entities/topics left without any
relationship go too. Articles with ``pinned = true`` are never deleted.

The size guard measures usage against the configured limits: warn from WARN_AT, refuse to write
from REFUSE_AT, so a full database fails loudly instead of rejecting writes halfway through a run.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass

from graphdb.connection import Neo4jClient

log = logging.getLogger(__name__)

WARN_AT = 0.80
REFUSE_AT = 0.95


class GraphFullError(RuntimeError):
    pass


@dataclass(frozen=True)
class GraphLimits:
    max_nodes: int = 200_000
    max_relationships: int = 400_000


@dataclass
class GraphSize:
    nodes: int
    relationships: int
    usage: float  # the fuller of the two, 0..1


def graph_size(client: Neo4jClient, limits: GraphLimits = GraphLimits()) -> GraphSize:
    nodes = int(client.run("MATCH (n) RETURN count(n) AS n")[0]["n"])
    rels = int(client.run("MATCH ()-[r]->() RETURN count(r) AS n")[0]["n"])
    return GraphSize(nodes, rels, round(max(nodes / limits.max_nodes, rels / limits.max_relationships), 6))


def check_capacity(client: Neo4jClient, limits: GraphLimits = GraphLimits()) -> GraphSize:
    size = graph_size(client, limits)
    fields = {"nodes": size.nodes, "relationships": size.relationships, "usage": size.usage}
    if size.usage >= REFUSE_AT:
        raise GraphFullError(f"graph is {size.usage:.0%} full ({size.nodes} nodes, {size.relationships} relationships): "
                             "refusing to write; shorten retention_days or move to a larger database")
    if size.usage >= WARN_AT:
        log.warning("graph nearly full", extra={"fields": fields})
    return size


_EXPIRED = "MATCH (a:Article) WHERE a.date < date($cutoff) AND NOT coalesce(a.pinned, false)"


def retention_preview(client: Neo4jClient, keep_days: int, today: dt.date) -> dict[str, int]:
    cutoff = (today - dt.timedelta(days=keep_days)).isoformat()
    row = client.run(_EXPIRED + " OPTIONAL MATCH (a)-[:DESCRIBES]->(e:Event) "
                     "RETURN count(DISTINCT a) AS articles, count(DISTINCT e) AS events", {"cutoff": cutoff})[0]
    return {"cutoff": cutoff, "articles": int(row["articles"]), "events": int(row["events"])}


def apply_retention(client: Neo4jClient, keep_days: int, today: dt.date) -> dict[str, int]:
    """Delete expired (unpinned) articles, their events, and orphaned entities/topics."""

    from graphdb.writer import _rebuild_precedes

    preview = retention_preview(client, keep_days, today)
    if preview["articles"]:
        # Batched so a large first cleanup doesn't build one huge transaction.
        client.run(_EXPIRED + " MATCH (a)-[:DESCRIBES]->(e:Event) "
                   "CALL { WITH e DETACH DELETE e } IN TRANSACTIONS OF 500 ROWS", {"cutoff": preview["cutoff"]})
        client.run(_EXPIRED + " CALL { WITH a DETACH DELETE a } IN TRANSACTIONS OF 500 ROWS", {"cutoff": preview["cutoff"]})
    orphans = int(client.run("MATCH (n) WHERE (n:Entity OR n:Topic) AND NOT (n)--() "
                             "WITH collect(n) AS ns FOREACH (n IN ns | DELETE n) RETURN size(ns) AS n")[0]["n"])
    if preview["articles"]:
        client.execute_write(_rebuild_precedes)  # deleted events leave gaps in the time chain
    result = {**preview, "orphans": orphans}
    log.info("retention applied", extra={"fields": result})
    return result
