from __future__ import annotations

import csv
import datetime as dt
from typing import Any

from graphdb.export import (
    EVENT_KEY_COLUMNS,
    export_event_keys,
    export_from_graph,
    write_event_keys_csv,
)
from graphdb.queries import date_key


class FakeExportClient:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows

    def run(self, query: str, parameters=None, database=None):
        assert "MATCH (e:Event)" in query
        return self.rows


def row(
    event_id: str,
    date: dt.date,
    date_source: str = "explicit",
    event_type: str = "general",
    article_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "date": date,
        "date_source": date_source,
        "type": event_type,
        "article_ids": article_ids if article_ids is not None else ["art_1"],
    }


def test_event_key_columns_match_pipeline_contract():
    from pipeline.export import EVENT_KEY_COLUMNS as PIPELINE_COLUMNS

    assert EVENT_KEY_COLUMNS == PIPELINE_COLUMNS


def test_export_event_keys_sorts_by_date_key_then_event_id():
    client = FakeExportClient(
        [
            row("evt_b", dt.date(2026, 3, 2)),
            row("evt_a", dt.date(2026, 3, 1)),
            row("evt_c", dt.date(2026, 3, 1)),
        ]
    )

    exported = export_event_keys(client)

    assert [item["event_id"] for item in exported] == ["evt_a", "evt_c", "evt_b"]
    assert exported[0]["date_key"] == date_key(dt.date(2026, 3, 1))
    assert exported[0]["date"] == "2026-03-01"


def test_missing_article_id_becomes_empty_string():
    client = FakeExportClient([row("evt_a", dt.date(2026, 3, 1), article_ids=[])])

    exported = export_event_keys(client)

    assert exported[0]["article_id"] == ""


def test_rows_without_date_are_skipped():
    client = FakeExportClient(
        [
            {
                "event_id": "evt_bad",
                "date": None,
                "date_source": "explicit",
                "type": "general",
                "article_ids": ["art_1"],
            }
        ]
    )

    assert export_event_keys(client) == []


def test_write_event_keys_csv_writes_stable_header_and_rows(tmp_path):
    rows = export_event_keys(FakeExportClient([row("evt_a", dt.date(2026, 3, 1))]))
    path = tmp_path / "keys.csv"

    count = write_event_keys_csv(rows, path)

    assert count == 1
    with open(path, newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        assert reader.fieldnames == EVENT_KEY_COLUMNS
        data = list(reader)
    assert data[0]["event_id"] == "evt_a"
    assert data[0]["date_key"] == str(date_key(dt.date(2026, 3, 1)))


def test_export_from_graph_returns_row_count(tmp_path):
    client = FakeExportClient([row("evt_a", dt.date(2026, 3, 1))])

    assert export_from_graph(client, tmp_path / "keys.csv") == 1
