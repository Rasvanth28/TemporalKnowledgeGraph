import argparse
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

from pipeline.config import load_extract_config, load_link_config
from pipeline.export import write_event_keys_csv, write_pipeline_json
from pipeline.extract import SpacyExtractor
from pipeline.ingest import JsonFileSource
from pipeline.run import run_pipeline


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="ingest -> extract -> link -> export")
    parser.add_argument("--input", default="data/sample_articles.json")
    parser.add_argument("--out-dir", default="data/exports")
    args = parser.parse_args()

    link_config = load_link_config()
    output = run_pipeline(JsonFileSource(args.input), SpacyExtractor(load_extract_config()), link_config)

    out_dir = Path(args.out_dir)
    write_pipeline_json(output, out_dir / "pipeline_output.json")
    n_keys = write_event_keys_csv(output.results, out_dir / "event_keys.csv")

    events = {e.event.id: e for r in output.results for e in r.events}
    print(f"articles: {len(output.results)}  events: {len(events)}  links: {len(output.links)}  (threshold {link_config.threshold})")
    print("event types:", dict(Counter(e.event.type for e in events.values())))
    for link in sorted(output.links, key=lambda l: -l.confidence)[:10]:
        a, b = events[link.from_event_id].event, events[link.to_event_id].event
        print(f"  {link.confidence:.2f} [{link.reason}]  {a.date} {a.description!r} -> {b.date} {b.description!r}")
    print(f"wrote {out_dir / 'pipeline_output.json'} and {out_dir / 'event_keys.csv'} ({n_keys} keys)")


if __name__ == "__main__":
    main()
