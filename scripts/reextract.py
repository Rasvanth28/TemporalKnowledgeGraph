"""Re-extract stored articles with the current pipeline: python -m scripts.reextract [--apply]

Dry run by default: prints what would change and writes nothing. Article text comes from
--input files (JSON, as written by scripts.fetch_guardian) and, for articles not found there,
from the Guardian API by URL (needs GUARDIAN_API_KEY).

Exit codes: 0 success, 1 configuration error, 2 run failure, 3 some articles had no text (dry run
still reports; --apply refuses unless --allow-missing).
"""

import argparse
import json
import logging
import os
import sys
from collections import Counter
from dataclasses import asdict

from dotenv import load_dotenv

from common.log import configure_logging
from pipeline.config import load_extract_config, load_link_config
from pipeline.extract import SpacyExtractor
from pipeline.guardian import GuardianError, fetch_article, retrying_session
from pipeline.ingest import JsonFileSource
from pipeline.reextract import apply_reextract, plan_reextract

log = logging.getLogger("reextract")


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", action="append", default=[], help="local article JSON (repeatable)")
    parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    parser.add_argument("--no-fetch", action="store_true", help="never call the Guardian API")
    parser.add_argument("--allow-missing", action="store_true", help="apply even if some articles have no text")
    args = parser.parse_args(argv)
    configure_logging()

    from common.embed import get_embedder
    from graphdb.config import ConfigurationError, load_neo4j_config
    from graphdb.connection import Neo4jClient
    from graphdb.search_index import embed_missing_events, ensure_search_indexes
    from graphdb.writer import PipelineWriter

    try:
        local = {raw.article.id: raw for path in args.input for raw in JsonFileSource(path).load()}
        neo4j_config = load_neo4j_config()
    except (OSError, ValueError, KeyError, ConfigurationError) as exc:
        log.error("configuration error: %s", exc)
        return 1
    api_key = "" if args.no_fetch else os.environ.get("GUARDIAN_API_KEY", "")
    session = retrying_session()

    def get_text(article_id, url):
        if article_id in local:
            return local[article_id]
        if not api_key:
            return None
        try:
            raw = fetch_article(api_key, url, session=session)
        except GuardianError as exc:
            log.warning("could not fetch article", extra={"fields": {"article_id": article_id, "error": str(exc)}})
            return None
        # Keep the stored id (it was derived from this URL) even if the API's URL form differs.
        if raw is not None:
            raw.article.id = article_id
        return raw

    try:
        with Neo4jClient(neo4j_config) as client:
            report, results = plan_reextract(client, SpacyExtractor(load_extract_config()), get_text)
            shifts = Counter(f"{old[:4]}->{new[:4]}" for c in report.changes for old, new in c.redated)
            print(json.dumps({"articles": report.articles, "articles_changing": len(report.changes),
                              "events_removed": report.events_removed, "events_added": report.events_added,
                              "missing_text": len(report.missing_text), "year_shifts": dict(shifts)}, indent=2))
            if not args.apply:
                print("dry run: nothing written (use --apply)")
                return 3 if report.missing_text else 0
            if report.missing_text and not args.allow_missing:
                log.error("refusing to apply: %d articles have no text (see --input / --allow-missing)", len(report.missing_text))
                return 3
            apply_reextract(client, report, results, PipelineWriter(client).write, load_link_config())
            embedder = get_embedder()
            if embedder is not None:
                ensure_search_indexes(client, embedder.dims)
                embed_missing_events(client, embedder)
            print(json.dumps({k: v for k, v in asdict(report).items() if k != "changes"} | {
                "events_removed": report.events_removed, "events_added": report.events_added}, indent=2, default=str))
    except Exception:
        log.exception("re-extraction failed")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
