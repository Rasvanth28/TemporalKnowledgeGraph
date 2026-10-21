"""Scheduled/incremental ingestion entry point: python -m scripts.ingest

Exit codes: 0 success (including "nothing new"), 1 configuration error, 2 run failure,
4 database (nearly) full: nothing was written.
"""

import argparse
import datetime
import json
import logging
import os
import sys
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

from common.log import configure_logging
from pipeline.config import load_extract_config, load_link_config
from pipeline.extract import SpacyExtractor
from pipeline.guardian import GuardianError, GuardianSource
from pipeline.wikipedia import WikipediaCurrentEventsSource
from pipeline.ingest_job import load_ingest_config, run_ingest

log = logging.getLogger("ingest")


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Fetch new articles and add them to the knowledge graph")
    parser.add_argument("--config", default="config/ingest_queries.json")
    parser.add_argument("--out-dir", default="data/exports")
    parser.add_argument("--dry-run", action="store_true", help="extract and link, but do not write to Neo4j")
    parser.add_argument("--since", type=datetime.date.fromisoformat,
                        help="backfill from this date (YYYY-MM-DD); clamped to the retention window")
    args = parser.parse_args(argv)
    configure_logging()

    from graphdb.capacity import GraphFullError
    from graphdb.config import ConfigurationError, load_neo4j_config
    from graphdb.connection import Neo4jClient
    from graphdb.export import export_event_keys, write_event_keys_csv
    from graphdb.search_index import embed_missing_events, ensure_search_indexes
    from graphdb.writer import PipelineWriter
    from common.embed import get_embedder

    api_key = os.environ.get("GUARDIAN_API_KEY", "")
    try:
        config = load_ingest_config(args.config)
        neo4j_config = load_neo4j_config()
        if not api_key:
            raise GuardianError("GUARDIAN_API_KEY is not set")
    except (OSError, ValueError, KeyError, ConfigurationError, GuardianError) as exc:
        log.error("configuration error: %s", exc)
        return 1

    def make_source(query, start, end):
        # Oldest-first: if a query hits max_per_query, the next run continues from where this one
        # stopped instead of silently skipping the remainder of the window.
        return GuardianSource(api_key, query.query, start, end, config.max_per_query, query.section, order_by="oldest")

    out_dir = Path(args.out_dir)
    try:
        with Neo4jClient(neo4j_config) as client:
            writer = None if args.dry_run else PipelineWriter(client).write
            extra = (lambda start, end: [WikipediaCurrentEventsSource(start, end)]) if config.wikipedia else None
            summary = run_ingest(config, make_source, SpacyExtractor(load_extract_config()), client, writer,
                                 load_link_config(), out_dir=out_dir, since=args.since, extra_sources=extra)
            if summary.written:
                keys = write_event_keys_csv(export_event_keys(client), out_dir / "event_keys.csv")
                log.info("exported event keys", extra={"fields": {"rows": keys, "path": str(out_dir / "event_keys.csv")}})
            # Every non-dry run, even with nothing new: this is also the backfill for older events.
            embedder = None if args.dry_run else get_embedder()
            if embedder is not None:
                ensure_search_indexes(client, embedder.dims)
                embedded = embed_missing_events(client, embedder)
                log.info("search index updated", extra={"fields": {"embedded": embedded}})
    except GraphFullError as exc:
        log.error("database full: %s", exc)
        return 4
    except Exception:
        log.exception("ingest failed")
        return 2

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ingest_summary.json").write_text(json.dumps(asdict(summary), indent=2, default=str))
    print(json.dumps(asdict(summary), default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
