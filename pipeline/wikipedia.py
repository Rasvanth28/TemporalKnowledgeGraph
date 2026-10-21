"""Wikipedia "Current events" portal as an article source (free, CC BY-SA 4.0).

Each day page (Portal:Current_events/2026_October_20) lists short, dated news items grouped by
category and nested under ongoing stories. Every leaf item is one self-contained sentence that cites
its original reporting ("... [https://www.reuters.com/... (Reuters)]"). Each leaf becomes one
RawArticle: the text is Wikipedia's (so it is credited to Wikipedia and links to the day page, as
the licence requires) and the original publisher is named in the source.

Wikimedia API etiquette: identify the client with a User-Agent and fetch pages sequentially.
"""

import datetime
import logging
import re

import requests

from common.schema import Article
from pipeline.extract import get_id
from pipeline.guardian import retrying_session
from pipeline.ingest import RawArticle

API_URL = "https://en.wikipedia.org/w/api.php"
PAGE_URL = "https://en.wikipedia.org/wiki/Portal:Current_events/{}"
USER_AGENT = "TemporalKnowledgeGraph/0.2 (https://github.com/Rasvanth28/TemporalKnowledgeGraph)"
SOURCE = "Wikipedia Current Events (CC BY-SA 4.0)"
MIN_WORDS = 6  # shorter leaves are story headings ("[[Abyei border conflict]]"), not news items

log = logging.getLogger(__name__)

_CITATION = re.compile(r"\[(https?://\S+)\s+\(?(?P<label>[^\]]*?)\)?\]")
_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
_REF = re.compile(r"<ref[^>]*?/>|<ref[^>]*>.*?</ref>", re.DOTALL)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_PIPED_LINK = re.compile(r"\[\[[^\]|]*\|([^\]]*)\]\]")
_LINK = re.compile(r"\[\[([^\]]*)\]\]")


def page_title(day: datetime.date) -> str:
    return f"{day.year}_{day.strftime('%B')}_{day.day}"


def clean(wikitext: str) -> tuple[str, list[str]]:
    """Plain sentence and the publishers it cites."""

    publishers = [re.sub(r"''+", "", m.group("label")).strip() for m in _CITATION.finditer(wikitext)]
    text = _CITATION.sub("", wikitext)
    text = _REF.sub("", _COMMENT.sub("", text))
    while _TEMPLATE.search(text):
        text = _TEMPLATE.sub("", text)
    text = _LINK.sub(r"\1", _PIPED_LINK.sub(r"\1", text))
    text = re.sub(r"''+", "", text)
    return " ".join(text.split()).strip(" ;"), [p for p in publishers if p]


def parse_day(wikitext: str, day: datetime.date) -> list[RawArticle]:
    """One RawArticle per leaf news item on a day page."""

    lines = [line.rstrip() for line in _COMMENT.sub("", wikitext).splitlines()]
    bullets = [(len(m.group(1)), m.group(2)) for line in lines if (m := re.match(r"^(\*+)\s*(.*)$", line))]
    url = PAGE_URL.format(page_title(day))
    raws = []
    for i, (depth, body) in enumerate(bullets):
        if i + 1 < len(bullets) and bullets[i + 1][0] > depth:
            continue  # a story heading with items under it
        text, publishers = clean(body)
        if len(text.split()) < MIN_WORDS:
            continue
        via = f" · original: {', '.join(dict.fromkeys(publishers))}" if publishers else ""
        article = Article(id=get_id(f"wikipedia-current-events:{day.isoformat()}:{text}"),
                          title=text if len(text) <= 160 else text[:159].rsplit(" ", 1)[0] + "…",
                          date=day, source=f"{SOURCE}{via}", url=url)
        raws.append(RawArticle(article=article, text=text))
    return raws


class WikipediaCurrentEventsSource:
    def __init__(self, start: datetime.date, end: datetime.date, session=None, timeout: float = 20):
        self.start, self.end = start, end
        self.session = session or retrying_session()
        self.timeout = timeout

    def _wikitext(self, day: datetime.date) -> str | None:
        resp = self.session.get(API_URL, timeout=self.timeout, headers={"User-Agent": USER_AGENT}, params={
            "action": "parse", "page": f"Portal:Current_events/{page_title(day)}", "prop": "wikitext",
            "format": "json", "formatversion": 2})
        resp.raise_for_status()
        body = resp.json()
        if "error" in body:
            return None  # no page for this day (yet)
        return body["parse"]["wikitext"]

    def load(self) -> list[RawArticle]:
        raws, day = [], self.start
        while day <= self.end:
            try:
                wikitext = self._wikitext(day)
            except requests.RequestException as exc:
                log.warning("wikipedia day failed", extra={"fields": {"day": day.isoformat(), "error": str(exc)}})
                wikitext = None
            if wikitext:
                raws.extend(parse_day(wikitext, day))
            day += datetime.timedelta(days=1)
        log.info("wikipedia fetch", extra={"fields": {"from": self.start.isoformat(), "to": self.end.isoformat(), "items": len(raws)}})
        return raws
