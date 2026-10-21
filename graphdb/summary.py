"""Extractive "what happened" summary for a prompt's results, without an LLM.

The summary is assembled only from the sources' own words, so every sentence can be cited:
the most relevant articles are chosen (by the summed relevance of their events), near-duplicate
stories are dropped, each article contributes its headline (or, when the headline is a question or
too short, its key sentence), the strongest articles add one supporting quote, and everything is
ordered by date and grouped into monthly paragraphs.
"""

from __future__ import annotations

import re
from typing import Any

MAX_ARTICLES = 10
DETAIL_ARTICLES = 3      # how many of the strongest articles also get a supporting quote
DETAIL_CHARS = 220
DUPLICATE_OVERLAP = 0.6  # word overlap above which two headlines tell the same story...
DUPLICATE_DAYS = 2       # ...if they were also published within this many days of each other

_HEADLINE_SUFFIX = re.compile(r"\s*(\||–|—)\s*(letters?|editorial|live|opinion|analysis|explainer)\s*$", re.IGNORECASE)
_WORD = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "of", "to", "in", "on", "for", "and", "at", "as", "by", "with", "is", "its", "it", "be"}


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall((text or "").lower()) if w not in _STOP}


def _overlap(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    return len(wa & wb) / min(len(wa), len(wb)) if wa and wb else 0.0


def _days_apart(a: str | None, b: str | None) -> int | None:
    import datetime as dt
    try:
        return abs((dt.date.fromisoformat(a) - dt.date.fromisoformat(b)).days)
    except (TypeError, ValueError):
        return None


def _duplicate(a: dict[str, Any], b: dict[str, Any]) -> bool:
    # Same story = similar headline AND published around the same time. Headlines about one subject
    # share its words ("Bank of England ... interest rates") without being the same story.
    days = _days_apart(a.get("date"), b.get("date"))
    return days is not None and days <= DUPLICATE_DAYS and _overlap(a.get("title") or "", b.get("title") or "") > DUPLICATE_OVERLAP


def _article_score(events: list[dict[str, Any]]) -> float:
    # Best event first, a little credit for the rest: long articles should not win on volume alone.
    scores = sorted((e.get("relevance", 0) for e in events), reverse=True)
    return scores[0] + 0.25 * sum(scores[1:]) if scores else 0.0


def _sentence(text: str) -> str:
    text = " ".join((text or "").split())
    return text if text[-1:] in ".!?…”\"" else f"{text}."


def headline_sentence(title: str | None) -> str | None:
    """A headline usable as a statement, or None (questions and fragments are not statements)."""

    title = _HEADLINE_SUFFIX.sub("", " ".join((title or "").split()))
    if not title or title.endswith("?") or len(title.split()) < 5:
        return None
    return _sentence(title)


def _shorten(text: str, limit: int = DETAIL_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1].rsplit(" ", 1)[0] + "…"


def build_summary(nodes: list[dict[str, Any]], sources: list[dict[str, Any]]) -> dict[str, Any]:
    events = [n for n in nodes if n.get("kind") == "event" and n.get("article_id")]
    by_article: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        by_article.setdefault(event["article_id"], []).append(event)
    source_by_id = {s["id"]: s for s in sources}

    ranked = sorted(by_article.items(), key=lambda item: (-_article_score(item[1]), item[0]))
    chosen: list[tuple[dict[str, Any], list[dict[str, Any]], float]] = []
    for article_id, article_events in ranked:
        source = source_by_id.get(article_id)
        if source is None:
            continue
        if any(_duplicate(source, other) for other, _, _ in chosen):
            continue  # same story reported again
        chosen.append((source, sorted(article_events, key=lambda e: -e.get("relevance", 0)), _article_score(article_events)))
        if len(chosen) == MAX_ARTICLES:
            break
    detail_ids = {s["id"] for s, _, _ in sorted(chosen, key=lambda c: -c[2])[:DETAIL_ARTICLES]}

    paragraphs: list[dict[str, Any]] = []
    for source, article_events, _ in sorted(chosen, key=lambda c: (c[0].get("date") or "", c[0]["id"])):
        top = article_events[0]
        statement = headline_sentence(source.get("title"))
        sentences = []
        if statement:
            sentences.append({"text": statement, "quote": False})
        quotes = [e for e in article_events if e.get("evidence")]
        # Add the key sentence when the headline can't stand alone, or as detail for the strongest stories.
        if quotes and (statement is None or source["id"] in detail_ids):
            quote = next((e for e in quotes if statement is None or _overlap(e["evidence"], statement) < 0.7), None)
            if quote is not None:
                sentences.append({"text": _shorten(quote["evidence"]), "quote": True, "event_node": quote["id"]})
        if not sentences:
            continue
        for sentence in sentences:
            sentence.setdefault("event_node", top["id"])
            sentence["article_id"] = source["id"]
        month = (source.get("date") or "")[:7]
        if paragraphs and paragraphs[-1]["month"] == month:
            paragraphs[-1]["sentences"].extend(sentences)
        else:
            paragraphs.append({"month": month, "sentences": sentences})

    dates = sorted(s.get("date") for s, _, _ in chosen if s.get("date"))
    return {
        "paragraphs": paragraphs,
        "articles_used": len(chosen),
        "articles_total": len(by_article),
        "start": dates[0] if dates else None,
        "end": dates[-1] if dates else None,
    }
