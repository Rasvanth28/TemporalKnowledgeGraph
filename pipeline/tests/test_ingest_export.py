import csv
import json
import datetime

import pytest

from common.schema import Article
from pipeline.export import date_key, write_event_keys_csv, write_pipeline_json
from pipeline.guardian import GuardianSource, GuardianError
from pipeline.ingest import JsonFileSource, RawArticle, save_articles_json
from pipeline.run import run_pipeline


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append(params)
        return self.pages[params["page"] - 1]


def guardian_item(n, body="The Bank of England raised interest rates in March 2024."):
    return {"webUrl": f"https://www.theguardian.com/business/{n}", "webTitle": f"Title {n}",
            "webPublicationDate": "2024-03-21T12:00:00Z", "fields": {"headline": f"Headline {n}", "bodyText": body}}


def test_json_round_trip(tmp_path):
    raw = RawArticle(Article(id="a1", title="T", date=datetime.date(2024,1,2), source="S", url="U"), "Text.")
    path = tmp_path / "articles.json"
    save_articles_json([raw], path)
    assert JsonFileSource(path).load() == [raw]

def test_guardian_source_paginates_and_skips_empty_bodies():
    pages = [
        FakeResponse({"response": {"status": "ok", "pages": 2, "results": [guardian_item(1), guardian_item(2, body="")]}}),
        FakeResponse({"response": {"status": "ok", "pages": 2, "results": [guardian_item(3)]}}),
    ]
    session = FakeSession(pages)
    raws = GuardianSource("key", "interest rates", max_articles=10, session=session).load()
    assert [r.article.title for r in raws] == ["Headline 1", "Headline 3"]
    assert raws[0].article.date == datetime.date(2024,3,21)
    assert raws[0].article.source == "The Guardian"
    assert session.calls[0]["show-fields"] == "headline,bodyText"

def test_guardian_source_rejects_bad_key():
    session = FakeSession([FakeResponse({}, status_code=401)])
    with pytest.raises(GuardianError):
        GuardianSource("bad", "q", session=session).load()
    with pytest.raises(GuardianError):
        GuardianSource("", "q")

def test_date_key_is_days_since_epoch():
    assert date_key(datetime.date(1970,1,2)) == 1

def test_pipeline_on_sample_dataset_exports_sorted_keys(tmp_path):
    output = run_pipeline(JsonFileSource("data/sample_articles.json"))
    assert len(output.results) == 3
    assert all(r.events for r in output.results)

    n = write_event_keys_csv(output.results, tmp_path / "keys.csv")
    with open(tmp_path / "keys.csv") as f:
        rows = list(csv.DictReader(f))
    keys = [int(r["date_key"]) for r in rows]
    assert n == len(rows) > 0 and keys == sorted(keys)

    write_pipeline_json(output, tmp_path / "out.json")
    data = json.loads((tmp_path / "out.json").read_text())
    event_ids = {e["event"]["id"] for r in data["results"] for e in r["events"]}
    assert all(lk["from_event_id"] in event_ids and lk["to_event_id"] in event_ids for lk in data["links"])

def test_guardian_reports_rate_limit_after_retries():
    session = FakeSession([FakeResponse({}, status_code=429)])
    with pytest.raises(GuardianError, match="rate limit"):
        GuardianSource("key", "q", session=session).load()

def test_retrying_session_retries_rate_limits_not_auth_errors():
    from pipeline.guardian import retrying_session
    retry = retrying_session().get_adapter("https://content.guardianapis.com").max_retries
    assert retry.total == 5 and 429 in retry.status_forcelist and 401 not in retry.status_forcelist
    assert retry.respect_retry_after_header


def test_fetch_article_by_url():
    from pipeline.guardian import fetch_article

    class ItemSession:
        def __init__(self, status=200):
            self.status, self.urls = status, []

        def get(self, url, params, timeout):
            self.urls.append(url)
            return FakeResponse({"response": {"status": "ok", "content": guardian_item(7)}}, status_code=self.status)

    session = ItemSession()
    raw = fetch_article("key", "https://www.theguardian.com/business/7", session=session)
    assert session.urls == ["https://content.guardianapis.com/business/7"]
    assert raw.article.title == "Headline 7"
    assert fetch_article("key", "https://www.theguardian.com/business/7", session=ItemSession(404)) is None
    with pytest.raises(GuardianError):
        fetch_article("key", "https://example.com/not-guardian", session=session)
