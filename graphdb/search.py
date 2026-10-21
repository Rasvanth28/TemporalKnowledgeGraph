"""Prompt -> knowledge-graph search, without an LLM.

A prompt like "how did UK interest rates change in 2024?" is interpreted in three local steps:

1. Entities: fuzzy-match the prompt against Entity names that exist in the graph (so only real
   nodes can match, and typos still work).
2. Dates: phrases like "in 2024", "since June 2024", "last 3 months", "between X and Y".
3. Keywords: what is left, searched with the Event full-text index (English stemming).

Events are retrieved by matched entities, by full-text keywords and by meaning (vector index over
event embeddings), merged with reciprocal-rank fusion, filtered by the date range, and the top
events are returned as a graph together with the entities and topics they connect to.

Parsing is pure (no I/O) so it is unit-tested directly; ``search_graph`` does the database work.
"""

from __future__ import annotations

import calendar
import datetime as dt
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from neo4j.exceptions import ClientError
from rapidfuzz import fuzz

from common.embed import Embedder
from graphdb.connection import Neo4jClient
from graphdb.search_index import EVENT_TEXT_INDEX, EVENT_VECTOR_INDEX
from graphdb.summary import build_summary

log = logging.getLogger(__name__)

DEFAULT_EVENTS = 30
MAX_EVENTS = 100
# Neo4j's vector index reports cosine rescaled to [0, 1] as (1 + cos) / 2. Calibrated on the Guardian
# sample: off-topic prompts ("chocolate cake recipe", "football transfers", gibberish) top out at
# 0.57-0.65; on-topic prompts start around 0.78. Below the floor, "nearest" events are noise.
MIN_VECTOR_SCORE = 0.70
# Scores also shift from prompt to prompt, so matches are kept relative to the best one; tighter when
# names/keywords already matched, because meaning should then only add near-equivalents.
MEANING_GAP_WITH_LEXICAL = 0.08
MEANING_GAP_ALONE = 0.12
RRF_K = 60
SOURCE_WEIGHTS = {"entity": 1.5, "keyword": 1.0, "meaning": 1.0}

STOPWORDS = set("""
a about above after again against all also am an and any are as at be because been before being below between
both but by can could did do does doing down during each few for from further had has have having he her here
hers herself him himself his how i if in into is it its itself just let me more most my myself no nor not now of
off on once only or other our ours ourselves out over own same she should show so some such tell than that the
their theirs them themselves then there these they this those through to too under until up very was we were
what when where which while who whom why will with would you your yours yourself yourselves news happen happened
happening change changed changes story stories event events give list find anything everything something
say says said tell told know think going get got make made
drove drive driving driven cause caused causing affect affected affecting impact impacted lead led behind
""".split())

MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
MONTHS["sept"] = 9
_MONTH = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_YEAR = r"((?:19|20)\d{2})"
# Non-capturing variants for composing patterns, so group numbers stay predictable.
_MONTH_NC = _MONTH.replace("(", "(?:", 1)
_YEAR_NC = r"(?:(?:19|20)\d{2})"
_POINT = rf"(?:{_MONTH_NC}\s+{_YEAR_NC}|{_YEAR_NC}|{_MONTH_NC})"
_UNITS = {"day": 1, "week": 7, "month": 30, "year": 365}
_LUCENE_SPECIAL = re.compile(r'([+\-&|!(){}\[\]^"~*?:\\/])')


@dataclass
class Interpretation:
    entities: list[dict[str, Any]] = field(default_factory=list)
    start: dt.date | None = None
    end: dt.date | None = None
    date_text: str | None = None
    keywords: list[str] = field(default_factory=list)


# ---------- dates ----------

def _month_range(year: int, month: int) -> tuple[dt.date, dt.date]:
    return dt.date(year, month, 1), dt.date(year, month, calendar.monthrange(year, month)[1])


def _point_range(text: str, today: dt.date) -> tuple[dt.date, dt.date] | None:
    """'June 2024' -> that month, '2024' -> that year, 'June' -> the most recent June."""

    m = re.fullmatch(rf"{_MONTH}\s+{_YEAR}", text, re.IGNORECASE)
    if m:
        return _month_range(int(m.group(2)), MONTHS[m.group(1).lower()])
    m = re.fullmatch(_YEAR, text)
    if m:
        return dt.date(int(m.group(1)), 1, 1), dt.date(int(m.group(1)), 12, 31)
    m = re.fullmatch(_MONTH, text, re.IGNORECASE)
    if m:
        month = MONTHS[m.group(1).lower()]
        year = today.year if month <= today.month else today.year - 1
        return _month_range(year, month)
    return None


def parse_dates(prompt: str, today: dt.date) -> tuple[dt.date | None, dt.date | None, str | None]:
    """Return (start, end, matched_text) for the first date phrase in the prompt, else (None, None, None)."""

    text = prompt.lower()
    m = re.search(rf"\b(?:between|from)\s+({_POINT})\s+(?:and|to|until|-)\s+({_POINT})\b", text)
    if m:
        a, b = _point_range(m.group(1), today), _point_range(m.group(2), today)
        if a and b:
            return min(a[0], b[0]), max(a[1], b[1]), m.group(0)
    m = re.search(r"\b(?:last|past|previous)\s+(\d+)\s+(day|week|month|year)s?\b", text)
    if m:
        return today - dt.timedelta(days=int(m.group(1)) * _UNITS[m.group(2)]), today, m.group(0)
    m = re.search(r"\b(?:last|past|previous)\s+(week|month|year)\b", text)
    if m:
        if m.group(1) == "year":
            return dt.date(today.year - 1, 1, 1), dt.date(today.year - 1, 12, 31), m.group(0)
        return today - dt.timedelta(days=_UNITS[m.group(1)]), today, m.group(0)
    m = re.search(r"\bthis\s+(year|month)\b", text)
    if m:
        start = dt.date(today.year, 1, 1) if m.group(1) == "year" else today.replace(day=1)
        return start, today, m.group(0)
    m = re.search(rf"\b(since|after|before|until|by)\s+({_POINT})\b", text)
    if m:
        point = _point_range(m.group(2), today)
        if point:
            if m.group(1) in {"since", "after"}:
                return point[0], today, m.group(0)
            return None, point[1], m.group(0)
    m = re.search(rf"\bq([1-4])\s+{_YEAR}\b", text)
    if m:
        q, year = int(m.group(1)), int(m.group(2))
        return dt.date(year, 3 * q - 2, 1), _month_range(year, 3 * q)[1], m.group(0)
    m = re.search(rf"\b(?:in\s+|during\s+)?({_MONTH}\s+{_YEAR}|{_YEAR})\b", text)
    if m:
        point = _point_range(m.group(1), today)
        if point:
            return point[0], point[1], m.group(0)
    m = re.search(rf"\b(?:in|during)\s+{_MONTH}\b", text)
    if m:
        point = _point_range(m.group(1), today)
        if point:
            return point[0], point[1], m.group(0)
    return None, None, None


# ---------- entities ----------

def match_entities(prompt: str, entities: list[dict[str, Any]], min_score: float = 88) -> list[dict[str, Any]]:
    """Entities whose names appear in the prompt, exactly or fuzzily, longest first.

    A name is skipped when its match lies inside a longer matched name ("Bank" in "Bank of England").
    Short all-caps names (UK, US, EU) must appear in capitals, so the word "us" does not match US.
    """

    lowered = prompt.lower()
    found: list[tuple[int, int, dict[str, Any]]] = []
    for entity in sorted(entities, key=lambda e: -len(e.get("name") or "")):
        name = (entity.get("name") or "").strip()
        if len(name) < 2:
            continue
        if len(name) <= 3:
            m = re.search(rf"(?<!\w){re.escape(name)}(?!\w)", prompt if name.isupper() else lowered,
                          0 if name.isupper() else re.IGNORECASE)
            if not m:
                continue
            span, score = (m.start(), m.end()), 100.0
        else:
            m = re.search(rf"(?<!\w){re.escape(name.lower())}(?!\w)", lowered)
            if m:
                span, score = (m.start(), m.end()), 100.0
            else:
                if len(name) < 5:
                    continue
                aligned = fuzz.partial_ratio_alignment(name.lower(), lowered)
                if aligned is None or aligned.score < min_score:
                    continue
                span, score = (aligned.dest_start, aligned.dest_end), float(aligned.score)
        if any(s <= span[0] and span[1] <= e for s, e, _ in found):
            continue
        found.append((span[0], span[1], {**entity, "score": round(score, 1), "span": span}))
    return [entity for _, _, entity in sorted(found, key=lambda f: f[0])]


# ---------- keywords ----------

def keywords_for(prompt: str, entities: list[dict[str, Any]], date_text: str | None) -> list[str]:
    # Remove the text each entity matched (its span, so typo'd names go too), then the date phrase.
    text = prompt.lower()
    for entity in sorted(entities, key=lambda e: -(e.get("span") or (0, 0))[0]):
        start, end = entity.get("span") or (0, 0)
        if end > start:
            text = text[:start] + " " + text[end:]
        else:
            text = re.sub(re.escape((entity.get("name") or "").lower()), " ", text)
    if date_text:
        text = text.replace(date_text, " ")
    words = re.findall(r"[a-z][a-z'\-]+", text)
    seen, out = set(), []
    for word in words:
        word = word.strip("'-")
        if len(word) < 3 or word in STOPWORDS or word in seen:
            continue
        seen.add(word)
        out.append(word)
    return out[:12]


def lucene_query(keywords: list[str]) -> str:
    # Escape Lucene syntax so a prompt can never break or steer the query; lowercase keeps
    # AND/OR/NOT from being read as operators.
    return " ".join(_LUCENE_SPECIAL.sub(r"\\\1", k.lower()) for k in keywords)


def interpret(prompt: str, known_entities: list[dict[str, Any]], today: dt.date) -> Interpretation:
    start, end, date_text = parse_dates(prompt, today)
    entities = match_entities(prompt, known_entities)
    return Interpretation(entities=entities, start=start, end=end, date_text=date_text,
                          keywords=keywords_for(prompt, entities, date_text))


def fuse(rankings: dict[str, list[str]], weights: dict[str, float] = SOURCE_WEIGHTS) -> list[tuple[str, float]]:
    """Reciprocal-rank fusion: robust to the different score scales of each retriever."""

    scores: dict[str, float] = {}
    for source, ids in rankings.items():
        for rank, event_id in enumerate(ids):
            scores[event_id] = scores.get(event_id, 0.0) + weights.get(source, 1.0) / (RRF_K + rank + 1)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


# ---------- database ----------

_DATE_FILTER = "($start IS NULL OR e.date >= date($start)) AND ($end IS NULL OR e.date <= date($end))"

_ALL_ENTITIES = "MATCH (n:Entity) RETURN n.id AS id, n.name AS name, n.type AS type LIMIT 50000"

_BY_ENTITY = f"""
MATCH (e:Event)-[:INVOLVES]->(n:Entity) WHERE n.id IN $ids AND {_DATE_FILTER}
WITH e, count(DISTINCT n) AS hits
RETURN e.id AS id ORDER BY hits DESC, e.date DESC LIMIT $k
"""

_BY_KEYWORD = f"""
CALL db.index.fulltext.queryNodes('{EVENT_TEXT_INDEX}', $q, {{limit: $k}}) YIELD node AS e, score
WHERE {_DATE_FILTER}
RETURN e.id AS id ORDER BY score DESC
"""

_BY_MEANING = f"""
CALL db.index.vector.queryNodes('{EVENT_VECTOR_INDEX}', $k, $vector) YIELD node AS e, score
WHERE score >= $min_score AND {_DATE_FILTER}
RETURN e.id AS id, score ORDER BY score DESC
"""

_BY_DATE_ONLY = f"""
MATCH (e:Event) WHERE {_DATE_FILTER}
OPTIONAL MATCH (e)-[r:LINKED_TO]-()
WITH e, count(r) AS degree
RETURN e.id AS id ORDER BY degree DESC, e.date DESC LIMIT $k
"""

_SUBGRAPH_EVENTS = """
UNWIND $ids AS id
MATCH (e:Event {id: id})
OPTIONAL MATCH (a:Article)-[:DESCRIBES]->(e)
OPTIONAL MATCH (e)-[:INVOLVES]->(n:Entity)
OPTIONAL MATCH (e)-[:ABOUT]->(t:Topic)
RETURN e.id AS id, e.description AS description, toString(e.date) AS date, e.type AS type,
       e.date_source AS date_source, min(a.id) AS article_id, e.source_text AS source_text,
       head(collect(DISTINCT a {.id, .title, .url, .source, date: toString(a.date)})) AS article,
       [x IN collect(DISTINCT {id: n.id, name: n.name, type: n.type}) WHERE x.id IS NOT NULL] AS entities,
       [x IN collect(DISTINCT t.name) WHERE x IS NOT NULL AND x <> 'general'] AS topics
"""

_COVERAGE = """
UNWIND $ids AS id
MATCH (e:Event {id: id})
OPTIONAL MATCH (e)-[:INVOLVES]->(n:Entity)
RETURN e.id AS id, coalesce(e.description, '') + ' ' + coalesce(e.source_text, '') AS text, collect(n.id) AS entity_ids
"""


def _coverage(client: Neo4jClient, event_ids: list[str], meaning: Interpretation) -> dict[str, tuple[bool, list[str]]]:
    if not event_ids or not (meaning.entities or meaning.keywords):
        return {}  # date-only (or empty) questions: everything in range answers them
    names = {e["id"]: e["name"] for e in meaning.entities}
    return {row["id"]: answers_directly(names, meaning.keywords, set(row["entity_ids"]), row["text"])
            for row in client.run(_COVERAGE, {"ids": event_ids})}


_SUBGRAPH_LINKS = """
MATCH (a:Event)-[r:LINKED_TO]->(b:Event)
WHERE a.id IN $ids AND b.id IN $ids
RETURN a.id AS source, b.id AS target, r.confidence AS confidence, r.reason AS reason
"""


def _ids(rows: list[dict[str, Any]]) -> list[str]:
    return [str(row["id"]) for row in rows if row.get("id")]


def _optional(client: Neo4jClient, query: str, params: dict[str, Any], what: str) -> list[dict[str, Any]]:
    # The full-text/vector indexes are created by ingestion. Until they exist (fresh deploy), skip that
    # retriever instead of failing the whole search: name matching still works.
    try:
        return client.run(query, params)
    except ClientError as exc:
        log.warning("search index unavailable, skipping", extra={"fields": {"retriever": what, "error": exc.code}})
        return []


def meaning_cutoff(scores: list[float], lexical_hits: bool) -> float:
    if not scores:
        return MIN_VECTOR_SCORE
    gap = MEANING_GAP_WITH_LEXICAL if lexical_hits else MEANING_GAP_ALONE
    return max(MIN_VECTOR_SCORE, max(scores) - gap)


def search_graph(client: Neo4jClient, prompt: str, embedder: Embedder | None = None,
                 today: dt.date | None = None, limit: int = DEFAULT_EVENTS) -> dict[str, Any]:
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("prompt must not be empty")
    if len(prompt) > 500:
        raise ValueError("prompt must be at most 500 characters")
    limit = max(1, min(int(limit), MAX_EVENTS))
    today = today or dt.date.today()

    meaning = interpret(prompt, client.run(_ALL_ENTITIES), today)
    dates = {"start": meaning.start.isoformat() if meaning.start else None,
             "end": meaning.end.isoformat() if meaning.end else None}
    k = max(limit * 3, 50)

    rankings: dict[str, list[str]] = {}
    if meaning.entities:
        rankings["entity"] = _ids(client.run(_BY_ENTITY, {**dates, "ids": [e["id"] for e in meaning.entities], "k": k}))
    if meaning.keywords:
        rankings["keyword"] = _ids(_optional(client, _BY_KEYWORD, {**dates, "q": lucene_query(meaning.keywords), "k": k}, "keyword"))
    if embedder is not None:
        vector = embedder.encode([prompt])[0]
        rows = _optional(client, _BY_MEANING, {**dates, "vector": vector, "k": k, "min_score": MIN_VECTOR_SCORE}, "meaning")
        cutoff = meaning_cutoff([r["score"] for r in rows], any(rankings.values()))
        rankings["meaning"] = [str(r["id"]) for r in rows if r["score"] >= cutoff]
    if not any(rankings.values()) and (meaning.start or meaning.end):
        rankings["date"] = _ids(client.run(_BY_DATE_ONLY, {**dates, "k": limit}))

    fused = fuse(rankings)[:max(limit * 3, 60)]
    coverage = _coverage(client, [event_id for event_id, _ in fused], meaning)
    # Events that answer the whole question first; partial ("related") matches after them.
    ranked = sorted(fused, key=lambda item: (not coverage.get(item[0], (False, []))[0], -item[1]))[:limit]
    graph = build_graph(client, [event_id for event_id, _ in ranked], {e["id"] for e in meaning.entities})
    relevance = dict(ranked)
    found_by = {source: set(ids) for source, ids in rankings.items()}
    matched_ids = {e["id"] for e in meaning.entities}
    involved: dict[str, list[str]] = {}
    for edge in graph["edges"]:
        if edge["kind"] == "involves" and edge["target"][2:] in matched_ids:
            involved.setdefault(edge["source"], []).append(edge["target"])
    names = {n["id"]: n["label"] for n in graph["nodes"] if n["kind"] == "entity"}
    for node in graph["nodes"]:
        if node["kind"] != "event":
            continue
        node["relevance"] = round(relevance.get(node["event_id"], 0.0) * RRF_K, 3)
        # Why this event is in the results, in terms the UI can explain.
        direct, missing = coverage.get(node["event_id"], (True, []))
        node["match"] = "direct" if direct else "related"
        node["why"] = {
            "missing": missing,
            "names": [names[n] for n in involved.get(node["id"], [])],
            "keywords": keyword_hits(meaning.keywords, f"{node['label']} {node.get('evidence') or ''}")
            if node["event_id"] in found_by.get("keyword", ()) else [],
            "meaning": node["event_id"] in found_by.get("meaning", ()),
            "in_date_range": bool(meaning.start or meaning.end),
        }
    events = [node for node in graph["nodes"] if node["kind"] == "event"]
    direct_events = [node for node in events if node["match"] == "direct"]
    return {
        "query": prompt,
        "interpretation": {
            "entities": [{k: e.get(k) for k in ("id", "name", "type", "score")} for e in meaning.entities],
            "start": dates["start"], "end": dates["end"], "date_text": meaning.date_text,
            "keywords": meaning.keywords, "semantic": embedder is not None,
        },
        **graph,
        "coverage": {"direct": len(direct_events), "related": len(events) - len(direct_events)},
        # Summarise the direct answers when there are any, so related news doesn't pose as the answer.
        "summary": build_summary(direct_events or events, graph["sources"]),
    }


def build_graph(client: Neo4jClient, event_ids: list[str], matched_entity_ids: set[str] = frozenset()) -> dict[str, Any]:
    """Events plus the entities/topics they connect to, as nodes and edges for a force layout."""

    if not event_ids:
        return {"nodes": [], "edges": [], "sources": []}
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    sources: dict[str, dict[str, Any]] = {}
    for row in client.run(_SUBGRAPH_EVENTS, {"ids": event_ids}):
        event_node = f"e:{row['id']}"
        nodes[event_node] = {"id": event_node, "kind": "event", "event_id": row["id"], "label": row["description"],
                             "date": row["date"], "type": row["type"], "date_source": row["date_source"],
                             "article_id": row["article_id"], "evidence": evidence_quote(row.get("source_text"))}
        article = row.get("article")
        if article and article.get("id"):
            sources.setdefault(article["id"], {"id": article["id"], "title": article.get("title"),
                                               "url": article.get("url"), "publisher": article.get("source"),
                                               "date": article.get("date")})
        for entity in row["entities"]:
            node_id = f"n:{entity['id']}"
            nodes.setdefault(node_id, {"id": node_id, "kind": "entity", "entity_id": entity["id"],
                                       "label": entity["name"], "type": entity["type"],
                                       "matched": entity["id"] in matched_entity_ids})
            edges.append({"source": event_node, "target": node_id, "kind": "involves"})
        for topic in row["topics"]:
            node_id = f"t:{topic}"
            nodes.setdefault(node_id, {"id": node_id, "kind": "topic", "label": topic})
            edges.append({"source": event_node, "target": node_id, "kind": "about"})
    for row in client.run(_SUBGRAPH_LINKS, {"ids": event_ids}):
        edges.append({"source": f"e:{row['source']}", "target": f"e:{row['target']}", "kind": "linked_to",
                      "confidence": float(row["confidence"] or 0.0), "reason": row["reason"] or ""})
    degree: dict[str, int] = {}
    for edge in edges:
        degree[edge["source"]] = degree.get(edge["source"], 0) + 1
        degree[edge["target"]] = degree.get(edge["target"], 0) + 1
    for node_id, node in nodes.items():
        node["degree"] = degree.get(node_id, 0)
    ordered_sources = sorted(sources.values(), key=lambda a: (a.get("date") or "", a["id"]))
    return {"nodes": list(nodes.values()), "edges": edges, "sources": ordered_sources}


EVIDENCE_CHARS = 280


def evidence_quote(text: str | None) -> str | None:
    """The sentence an event was extracted from, shortened to a quote (shown with a link to the source)."""

    text = " ".join((text or "").split())
    if not text:
        return None
    return text if len(text) <= EVIDENCE_CHARS else text[:EVIDENCE_CHARS - 1].rsplit(" ", 1)[0] + "…"


# Everyday news words that mean the same thing for search ("gas price" should match "petrol costs").
# Deliberately small: each entry widens what counts as a direct answer.
RELATED_TERMS = {
    "gas": {"petrol", "gasoline", "fuel"}, "petrol": {"gas", "gasoline", "fuel"}, "gasoline": {"gas", "petrol", "fuel"},
    "fuel": {"petrol", "gasoline", "diesel"}, "price": {"cost", "pricing"}, "cost": {"price", "pricing"},
    "oil": {"crude", "petroleum", "brent"}, "crude": {"oil", "brent"}, "rate": {"rates"},
    "job": {"employment", "unemployment", "jobless"}, "unemployment": {"jobless", "employment"},
    "election": {"vote", "poll", "ballot"}, "war": {"conflict", "fighting", "invasion"},
    "tax": {"taxes", "levy", "duty"}, "mortgage": {"mortgages", "home loan"},
}


def stem(word: str) -> str:
    word = word.lower()
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("ing") and len(word) > 5:
        return word[:-3]
    if word.endswith("ed") and len(word) > 4:
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def term_forms(keyword: str) -> set[str]:
    base = stem(keyword)
    return {base} | {stem(t) for t in RELATED_TERMS.get(base, set()) | RELATED_TERMS.get(keyword.lower(), set())}


def term_covered(keyword: str, text: str | None) -> bool:
    lowered = (text or "").lower()
    return any(re.search(rf"\b{re.escape(form)}", lowered) for form in term_forms(keyword))


def keyword_hits(keywords: list[str], text: str | None) -> list[str]:
    return [k for k in keywords if term_covered(k, text)]


def answers_directly(entity_names: dict[str, str], keywords: list[str], involved: set[str], text: str) -> tuple[bool, list[str]]:
    """Does an event answer the whole question? Returns (direct, parts it does not cover).

    Every name asked about must be involved (or named in the text). Topic words: with names, at least
    one must be covered (the names already pin the subject); without names, at least half of them.
    """

    lowered = (text or "").lower()
    missing = [name for entity_id, name in entity_names.items() if entity_id not in involved and name.lower() not in lowered]
    hits = keyword_hits(keywords, lowered)
    missing_terms = [k for k in keywords if k not in hits]
    needed = 1 if entity_names else (len(keywords) + 1) // 2
    direct = not missing and (not keywords or len(hits) >= needed)
    return direct, missing + (missing_terms if len(hits) < needed else [])
