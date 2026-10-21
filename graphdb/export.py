"""Flat event-key export from the populated Neo4j graph.

The column contract is the same as ``pipeline/export.py``:
``event_id, date_key, date, date_source, type, article_id``, with
``date_key`` as days since 1970-01-01 and rows sorted by ``(date_key, event_id)``.

Unlike the pipeline export, this reads from the graph, proving that the graph is
populated and queryable.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

from graphdb.config import ConfigurationError, load_neo4j_config
from graphdb.connection import Neo4jClient
from graphdb.queries import date_key

EVENT_KEY_COLUMNS = ["event_id", "date_key", "date", "date_source", "type", "article_id"]

_EXPORT_QUERY = """
MATCH (e:Event)
OPTIONAL MATCH (a:Article)-[:DESCRIBES]->(e)
RETURN e.id AS event_id, e.date AS date, e.date_source AS date_source, e.type AS type,
       collect(DISTINCT a.id) AS article_ids
ORDER BY e.date, e.id
"""


def _iso_date(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "iso_format"):
        return value.iso_format()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    text = str(value)
    return text[:10] if len(text) >= 10 else text


def export_event_keys(client: Neo4jClient) -> list[dict[str, Any]]:
    """Read all events from Neo4j as flat event-key rows."""

    rows = client.run(_EXPORT_QUERY)
    exported: list[dict[str, Any]] = []
    for row in rows:
        event_id = str(row.get("event_id") or "")
        date_text = _iso_date(row.get("date"))
        if not event_id or not date_text:
            continue
        article_ids = [value for value in (row.get("article_ids") or []) if value]
        exported.append(
            {
                "event_id": event_id,
                "date_key": date_key(date_text),
                "date": date_text,
                "date_source": row.get("date_source") or "",
                "type": row.get("type") or "",
                "article_id": article_ids[0] if article_ids else "",
            }
        )
    exported.sort(key=lambda item: (item["date_key"], item["event_id"]))
    return exported


def write_event_keys_csv(rows: list[dict[str, Any]], path: str | Path) -> int:
    """Write event-key rows with the stable column order."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=EVENT_KEY_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in EVENT_KEY_COLUMNS})
    return len(rows)


def export_from_graph(client: Neo4jClient, path: str | Path) -> int:
    """Export the graph's event keys to CSV and return the row count."""

    return write_event_keys_csv(export_event_keys(client), path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export flat event-key rows from Neo4j for Person C's RMI lane."
    )
    parser.add_argument(
        "--output",
        default="data/exports/graph_event_keys.csv",
        help="CSV output path (default: data/exports/graph_event_keys.csv).",
    )
    args = parser.parse_args(argv)

    try:
        config = load_neo4j_config()
    except ConfigurationError as exc:
        print(f"Export configuration error: {exc}")
        return 1

    client = Neo4jClient(config)
    try:
        count = export_from_graph(client, args.output)
    except Exception as exc:
        print(f"Export failed: {type(exc).__name__}: {exc}")
        return 1
    finally:
        client.close()

    print(f"wrote {count} event keys to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
