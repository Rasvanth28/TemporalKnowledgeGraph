import csv
import json
import datetime
import dataclasses
from pathlib import Path

from common.schema import ExtractionResult, PipelineOutput

EPOCH = datetime.date(1970, 1, 1)
EVENT_KEY_COLUMNS = ["event_id", "date_key", "date", "date_source", "type", "article_id"]


def date_key(d: datetime.date) -> int:
    # Days since 1970-01-01: a numeric, sortable date key.
    return (d - EPOCH).days


def write_event_keys_csv(results: list[ExtractionResult], path: str | Path) -> int:
    rows = [
        {"event_id":e.event.id,"date_key":date_key(e.event.date),"date":e.event.date.isoformat(),
         "date_source":e.event.date_source,"type":e.event.type,"article_id":r.article.id}
        for r in results for e in r.events
    ]
    rows.sort(key=lambda row: (row["date_key"], row["event_id"]))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=EVENT_KEY_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def _json_default(value):
    if isinstance(value, datetime.date):
        return value.isoformat()
    raise TypeError(f"not JSON serialisable: {type(value)}")


def write_pipeline_json(output: PipelineOutput, path: str | Path) -> None:
    # Full nested output for the graph lane's writer (Article/Event/Entity/Topic + links).
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dataclasses.asdict(output), f, indent=2, ensure_ascii=False, default=_json_default)
