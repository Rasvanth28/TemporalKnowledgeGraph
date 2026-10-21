"""Pin articles so the rolling-window retention never deletes them: python -m scripts.pin_articles

    --all-existing      pin every article currently in the graph (e.g. a curated set before retention starts)
    --id ID [--id ...]  pin specific articles
    --unpin             remove the pin instead
"""

import argparse
import sys

from dotenv import load_dotenv


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Pin articles so retention keeps them")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all-existing", action="store_true")
    group.add_argument("--id", action="append")
    parser.add_argument("--unpin", action="store_true")
    args = parser.parse_args(argv)

    from graphdb.config import load_neo4j_config
    from graphdb.connection import Neo4jClient

    where = "" if args.all_existing else "WHERE a.id IN $ids"
    with Neo4jClient(load_neo4j_config()) as client:
        rows = client.run(f"MATCH (a:Article) {where} SET a.pinned = $pinned RETURN count(a) AS n",
                          {"ids": args.id or [], "pinned": not args.unpin})
    print(f"{'unpinned' if args.unpin else 'pinned'} {rows[0]['n']} articles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
