import datetime
import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from common.schema import Article
from pipeline.extract import get_id
from pipeline.ingest import RawArticle

GUARDIAN_URL = "https://content.guardianapis.com/search"
MAX_PAGE_SIZE = 50

log = logging.getLogger(__name__)


def retrying_session(retries: int = 5, backoff: float = 2.0) -> requests.Session:
    # Rate limits (429) and transient server errors are retried with exponential backoff,
    # honouring Retry-After. Auth errors (401/403) are not retried.
    retry = Retry(total=retries, backoff_factor=backoff, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=frozenset({"GET"}), respect_retry_after_header=True, raise_on_status=False)
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


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
        self.session = session or retrying_session()
        self.timeout = timeout

    def _params(self, page: int) -> dict:
        params = {
            "api-key": self.api_key,
            "show-fields": "headline,bodyText",
            "page-size": min(MAX_PAGE_SIZE, self.max_articles),
            "page": page,
            "order-by": self.order_by,
            "type": "article",
        }
        if self.query:  # no query = every article in the window
            params["q"] = self.query
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
        if resp.status_code == 429:
            raise GuardianError("Guardian API rate limit still exceeded after retries")
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
        raws, seen = [], set()
        page, pages, total = 1, 1, 0
        while page <= pages and len(raws) < self.max_articles:
            body = self._get(page)
            pages = body.get("pages", 1)
            total = body.get("total", 0)
            for item in body.get("results", []):
                raw = self.parse_result(item)
                # Pages can shift while paging (new articles published), repeating items.
                if raw is not None and raw.article.id not in seen:
                    seen.add(raw.article.id)
                    raws.append(raw)
            page += 1
        log.info("guardian fetch", extra={"fields": {"query": self.query, "articles": min(len(raws), self.max_articles), "available": total}})
        if total > self.max_articles:
            log.warning("guardian results capped", extra={"fields": {"query": self.query, "available": total, "max_articles": self.max_articles}})
        return raws[:self.max_articles]


def fetch_article(api_key: str, url: str, session=None, timeout: float = 20) -> RawArticle | None:
    """Re-fetch one Guardian article by its web URL (used to re-extract stored articles)."""

    if not api_key:
        raise GuardianError("GUARDIAN_API_KEY is not set")
    prefix = "https://www.theguardian.com/"
    if not url.startswith(prefix):
        raise GuardianError(f"not a Guardian article URL: {url}")
    session = session or retrying_session()
    resp = session.get(f"https://content.guardianapis.com/{url[len(prefix):]}",
                       params={"api-key": api_key, "show-fields": "headline,bodyText"}, timeout=timeout)
    if resp.status_code in (401, 403):
        raise GuardianError("Guardian API rejected the key (check GUARDIAN_API_KEY)")
    if resp.status_code == 404:
        return None  # removed by the publisher
    resp.raise_for_status()
    content = resp.json().get("response", {}).get("content")
    return GuardianSource.parse_result(content) if content else None
