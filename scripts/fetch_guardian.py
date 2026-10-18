import argparse
import datetime
import os

from dotenv import load_dotenv

from pipeline.guardian import GuardianSource
from pipeline.ingest import save_articles_json


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Fetch Guardian articles into a pipeline input file")
    parser.add_argument("--query", action="append", required=True,
                        help="search query; repeat to pull several event chains")
    parser.add_argument("--from-date", type=datetime.date.fromisoformat)
    parser.add_argument("--to-date", type=datetime.date.fromisoformat)
    parser.add_argument("--max-per-query", type=int, default=10)
    parser.add_argument("--section", help="e.g. business, politics, world")
    parser.add_argument("--out", default="data/guardian_articles.json")
    args = parser.parse_args()

    by_id = {}
    for query in args.query:
        source = GuardianSource(os.environ.get("GUARDIAN_API_KEY", ""), query, args.from_date,
                                args.to_date, args.max_per_query, args.section)
        fetched = source.load()
        print(f"{query!r}: {len(fetched)} articles")
        for raw in fetched:
            by_id.setdefault(raw.article.id, raw)

    raws = sorted(by_id.values(), key=lambda r: r.article.date)
    save_articles_json(raws, args.out)
    print(f"wrote {len(raws)} articles to {args.out}")


if __name__ == "__main__":
    main()
