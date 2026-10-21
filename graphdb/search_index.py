"""Search indexes (full-text + vector) and event embeddings.

Kept separate from the four core indexes in ``indexes.cql``: these serve prompt search only and
depend on the embedding model's dimensions. Everything here is idempotent; ingestion calls
``ensure_search_indexes`` and ``embed_missing_events`` after every write, which also backfills
events written before embeddings existed.

    python -m graphdb.search_index    # apply indexes + embed any events that need it
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from common.embed import Embedder, event_text
from graphdb.connection import Neo4jClient

log = logging.getLogger(__name__)

EVENT_TEXT_INDEX = "event_text"
ENTITY_NAME_INDEX = "entity_name_text"
EVENT_VECTOR_INDEX = "event_embedding"


def search_index_statements(dims: int) -> list[str]:
    return [
        # 'english' analyzer: stemming + stop words, so "rates" matches "rate".
        f"CREATE FULLTEXT INDEX {EVENT_TEXT_INDEX} IF NOT EXISTS FOR (e:Event) ON EACH [e.description, e.source_text] "
        "OPTIONS {indexConfig: {`fulltext.analyzer`: 'english'}}",
        f"CREATE FULLTEXT INDEX {ENTITY_NAME_INDEX} IF NOT EXISTS FOR (n:Entity) ON EACH [n.name]",
        f"CREATE VECTOR INDEX {EVENT_VECTOR_INDEX} IF NOT EXISTS FOR (e:Event) ON (e.embedding) "
        f"OPTIONS {{indexConfig: {{`vector.dimensions`: {int(dims)}, `vector.similarity_function`: 'cosine'}}}}",
    ]


def ensure_search_indexes(client: Neo4jClient, dims: int, wait_seconds: int = 120) -> None:
    for statement in search_index_statements(dims):
        client.run(statement)
    client.run(f"CALL db.awaitIndexes({int(wait_seconds)})")


_EVENTS_TO_EMBED = """
MATCH (e:Event)
WHERE e.embedding IS NULL OR coalesce(e.embedding_model, '') <> $model
OPTIONAL MATCH (e)-[:INVOLVES]->(n:Entity)
OPTIONAL MATCH (e)-[:ABOUT]->(t:Topic)
WITH e, collect(DISTINCT n.name) AS entities, head(collect(DISTINCT t.name)) AS topic
RETURN e.id AS id, e.description AS description, coalesce(e.source_text, '') AS source_text,
       entities, coalesce(topic, '') AS topic
LIMIT $batch
"""

_SET_EMBEDDINGS = """
UNWIND $rows AS row
MATCH (e:Event {id: row.id})
CALL db.create.setNodeVectorProperty(e, 'embedding', row.vector)
SET e.embedding_model = $model
"""


def embed_missing_events(client: Neo4jClient, embedder: Embedder, batch: int = 256) -> int:
    """Embed events that have no embedding (or one from a different model). Returns how many."""

    total = 0
    while True:
        rows: list[dict[str, Any]] = client.run(_EVENTS_TO_EMBED, {"model": embedder.name, "batch": batch})
        if not rows:
            break
        texts = [event_text(r["description"] or "", r["source_text"], r["entities"], r["topic"]) for r in rows]
        vectors = embedder.encode(texts)
        client.run(_SET_EMBEDDINGS, {"model": embedder.name,
                                     "rows": [{"id": r["id"], "vector": v} for r, v in zip(rows, vectors)]})
        total += len(rows)
    if total:
        log.info("embedded events", extra={"fields": {"events": total, "model": embedder.name}})
    return total


def main() -> int:  # pragma: no cover - thin CLI
    from common.embed import get_embedder
    from common.log import configure_logging
    from graphdb.config import load_neo4j_config

    configure_logging()
    embedder = get_embedder()
    if embedder is None:
        return 1
    with Neo4jClient(load_neo4j_config()) as client:
        ensure_search_indexes(client, embedder.dims)
        print(f"search indexes ready; embedded {embed_missing_events(client, embedder)} events")
    return 0


if __name__ == "__main__":
    sys.exit(main())
