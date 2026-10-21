"""Scheduled/incremental ingestion entry point: python -m scripts.ingest

Exit codes: 0 success (including "nothing new"), 1 configuration error, 2 run failure.
"""

import argparse
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
from pipeline.ingest_job import load_ingest_config, run_ingest

log = logging.getLogger("ingest")


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Fetch new articles and add them to the knowledge graph")
    parser.add_argument("--config", default="config/ingest_queries.json")
    parser.add_argument("--out-dir", default="data/exports")
    parser.add_argument("--dry-run", action="store_true", help="extract and link, but do not write to Neo4j")
    args = parser.parse_args(argv)
    configure_logging()

    from graphdb.config import ConfigurationError, load_neo4j_config
    from graphdb.connection import Neo4jClient
    from graphdb.export import export_event_keys, write_event_keys_csv
    from graphdb.writer import PipelineWriter

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
            summary = run_ingest(config, make_source, SpacyExtractor(load_extract_config()), client, writer,
                                 load_link_config(), out_dir=out_dir)
            if summary.written:
                keys = write_event_keys_csv(export_event_keys(client), out_dir / "event_keys.csv")
                log.info("exported event keys", extra={"fields": {"rows": keys, "path": str(out_dir / "event_keys.csv")}})
    except Exception:
        log.exception("ingest failed")
        return 2

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ingest_summary.json").write_text(json.dumps(asdict(summary), indent=2, default=str))
    print(json.dumps(asdict(summary), default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
