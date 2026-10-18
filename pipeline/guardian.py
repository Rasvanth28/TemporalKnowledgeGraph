import datetime

import requests

from common.schema import Article
from pipeline.extract import get_id
from pipeline.ingest import RawArticle

GUARDIAN_URL = "https://content.guardianapis.com/search"
MAX_PAGE_SIZE = 50


class GuardianError(RuntimeError):
    pass


class GuardianSource:
    # Guardian Open Platform search API (free key: https://open-platform.theguardian.com/access/).
    def __init__(self, api_key: str, query: str, from_date: datetime.date | None = None,
                 to_date: datetime.date | None = None, max_articles: int = 30,
                 section: str | None = None, order_by: str = "relevance", session=None, timeout: float = 20):
        if not api_key:
            raise GuardianError("GUARDIAN_API_KEY is not set")
        self.api_key = api_key
        self.query = query
        self.from_date = from_date
        self.to_date = to_date
        self.max_articles = max_articles
        self.section = section
        self.order_by = order_by
        self.session = session or requests.Session()
        self.timeout = timeout

    def _params(self, page: int) -> dict:
        params = {
            "q": self.query,
            "api-key": self.api_key,
            "show-fields": "headline,bodyText",
            "page-size": min(MAX_PAGE_SIZE, self.max_articles),
            "page": page,
            "order-by": self.order_by,
            "type": "article",
        }
        if self.from_date:
            params["from-date"] = self.from_date.isoformat()
        if self.to_date:
            params["to-date"] = self.to_date.isoformat()
        if self.section:
            params["section"] = self.section
        return params

    def _get(self, page: int) -> dict:
        resp = self.session.get(GUARDIAN_URL, params=self._params(page), timeout=self.timeout)
        if resp.status_code == 401 or resp.status_code == 403:
            raise GuardianError("Guardian API rejected the key (check GUARDIAN_API_KEY)")
        resp.raise_for_status()
        body = resp.json().get("response", {})
        if body.get("status") != "ok":
            raise GuardianError(body.get("message", "Guardian API returned an error"))
        return body

    @staticmethod
    def parse_result(item: dict) -> RawArticle | None:
        fields = item.get("fields", {})
        text = (fields.get("bodyText") or "").strip()
        if not text:
            return None
        article = Article(
            id=get_id(item["webUrl"]),
            title=fields.get("headline") or item.get("webTitle", ""),
            date=datetime.date.fromisoformat(item["webPublicationDate"][:10]),
            source="The Guardian",
            url=item["webUrl"],
        )
        return RawArticle(article=article, text=text)

    def load(self) -> list[RawArticle]:
        raws = []
        page, pages = 1, 1
        while page <= pages and len(raws) < self.max_articles:
            body = self._get(page)
            pages = body.get("pages", 1)
            for item in body.get("results", []):
                raw = self.parse_result(item)
                if raw is not None:
                    raws.append(raw)
            page += 1
        return raws[:self.max_articles]
