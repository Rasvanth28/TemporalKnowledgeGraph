import re
import uuid
import datetime
from typing import Protocol

import dateutil.parser
import spacy
from spacy.tokens import Doc, Span

from common.schema import Article, Entity, Event, Topic, ExtractedEvent, ExtractionResult
from pipeline.config import ExtractConfig

LABEL_MAP = {"ORG":"ORG","PERSON":"PERSON","GPE":"LOCATION","LOC":"LOCATION", "LAW":"POLICY"}
POLICY_KEYWORDS = {"encryption policy","access control","quantitative easing"}

# Checked in order against lemmas: the sentence's main verb first, then every token.
EVENT_TYPE_KEYWORDS = {
    "policy_change": {"raise","cut","hike","rate","approve","pass","ban","introduce","reform","sanction","legislate"},
    "economic": {"grow","shrink","inflation","gdp","recession","unemployment","economy","budget","deficit","subvention","tax"},
    "election": {"elect","election","vote","referendum","campaign","poll"},
    "conflict": {"attack","invade","war","kill","protest","clash","strike"},
    "agreement": {"sign","agree","deal","treaty","negotiate","summit"},
    "legal": {"sue","court","convict","charge","investigate","rule"},
}

SUBJECT_DEPS = {"nsubj","nsubjpass"}
OBJECT_DEPS = {"dobj","obj","attr"}
# "Bailey said rates would fall": the news is the clausal complement, not the act of saying.
REPORTING_VERBS = {"say","tell","add","state","claim","report","note","insist","argue","explain",
                   "write","believe","think","suggest","reckon","acknowledge","admit"}
COPULA_VERBS = {"be"}
RELATIVE_DATES = {"today":0,"yesterday":-1,"tomorrow":1}
MONTH_OR_YEAR = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b|\b(1[89]|20)\d{2}\b",
    re.IGNORECASE,
)

_nlp_cache = {}


def get_nlp(model: str = "en_core_web_sm"):
    if model not in _nlp_cache:
        _nlp_cache[model] = spacy.load(model)
    return _nlp_cache[model]


def _as_span(text_or_span) -> Doc | Span:
    if isinstance(text_or_span, str):
        return get_nlp()(text_or_span)
    return text_or_span


def _first_sentence(text_or_span) -> Span:
    span = _as_span(text_or_span)
    return next(iter(span.sents)) if isinstance(span, Doc) else span


def full_phrase(token):
    if (token is None):
        return None
    # A head inside a named entity gets the whole entity ("Bank" -> "Bank of England").
    for ent in token.doc.ents:
        if ent.start <= token.i < ent.end and ent.label_ in LABEL_MAP:
            return normalize_name(ent.text)
    words = [child for child in token.children if child.dep_ == "compound"]
    words.append(token)
    words.sort(key=lambda word:word.i)
    text = " ".join(w.text for w in words)
    return text


def event_head(sent: Span):
    # The verb the event is about: the sentence root, or the reported clause under a reporting verb.
    # None when a reporting verb has nothing reported ("she said.").
    root = sent.root
    if root.lemma_.lower() in REPORTING_VERBS:
        return next((c for c in root.children if c.dep_ in {"ccomp","xcomp"}), None)
    return root


def get_id(text : str) -> str:
    namespace = uuid.NAMESPACE_DNS
    unique_id = uuid.uuid5(namespace,text)
    return str(unique_id)


def normalize_name(name: str) -> str:
    # "The Federal Reserve" and "Federal Reserve" must become the same graph node.
    name = " ".join(name.split())
    name = re.sub(r"^the\s+", "", name, flags=re.IGNORECASE)
    name = re.sub(r"['’]s$", "", name)
    return name


def extract_policy_entities(text:str) -> list[Entity]:
    entities = []
    for policy in sorted(POLICY_KEYWORDS):
        if policy in text.lower():
            policy_id = get_id(policy+"POLICY")
            entities.append(Entity(id=policy_id,name=policy,type="POLICY"))
    return entities


def extract_entities(text_or_span) -> list[Entity]:
    # Deduped by name: spaCy can tag the same name PERSON in one sentence and ORG in another,
    # which would split one real-world entity into two graph nodes. First label wins.
    span = _as_span(text_or_span)
    entities = {}
    for ent in span.ents:
        if ent.label_ in LABEL_MAP:
            name = normalize_name(ent.text)
            if not name:
                continue
            ent_type = LABEL_MAP[ent.label_]
            ent_id = get_id(name.lower()+ent_type)
            entities.setdefault(name.lower(), Entity(id=ent_id,name=name,type=ent_type))
    for en in extract_policy_entities(span.text):
        entities.setdefault(en.name.lower(), en)
    return list(entities.values())


def parse_date(text: str, article_date: datetime.date) -> datetime.date | None:
    # Only accept DATE mentions that name a month or a year; "Tuesday" or "last quarter"
    # can't be resolved reliably, so the caller falls back to the article's date.
    lower = text.lower().strip()
    if lower in RELATIVE_DATES:
        return article_date + datetime.timedelta(days=RELATIVE_DATES[lower])
    if not MONTH_OR_YEAR.search(text):
        return None
    try:
        # Parse twice with different defaults to see which fields the text actually specified.
        start = dateutil.parser.parse(text, default=datetime.datetime(article_date.year, 1, 1), fuzzy=True).date()
        probe = dateutil.parser.parse(text, default=datetime.datetime(article_date.year, 12, 28), fuzzy=True).date()
    except (dateutil.parser.ParserError, ValueError, OverflowError):
        return None
    if not 1800 <= start.year <= article_date.year + 10:
        return None
    has_month, has_day = start.month == probe.month, start.day == probe.day
    # "in March 2024" inside an article published 15 March 2024 means "now", not 1 March;
    # otherwise an under-specified date resolves to the start of its period.
    if not has_day and start.year == article_date.year and (not has_month or start.month == article_date.month):
        return article_date
    return start


def extract_event_date(text_or_span, article_date: datetime.date) -> list[datetime.date]:
    span = _as_span(text_or_span)
    dates = []
    for ent in span.ents:
        if ent.label_ == "DATE":
            parsed = parse_date(ent.text, article_date)
            if parsed is not None:
                dates.append(parsed)
    return dates or [article_date]


def resolve_event_date(text_or_span, article_date: datetime.date) -> tuple[datetime.date, str]:
    # date_source tells linking whether the date came from the text or was inherited from the article.
    span = _as_span(text_or_span)
    has_explicit = any(e.label_ == "DATE" and parse_date(e.text, article_date) for e in span.ents)
    date = pick_event_date(extract_event_date(span, article_date))
    return date, "explicit" if has_explicit else "inferred"


def pick_event_date(dates: list[datetime.date])->datetime.date:
    return dates[0]


def _head(text_or_span):
    sent = _first_sentence(text_or_span)
    return event_head(sent) or sent.root


def classify_event_type(text_or_span)->str:
    # Only the event verb and its subject/object heads: scanning every token lets side clauses
    # ("..., cutting power") decide the type.
    head = _head(text_or_span)
    head_lemma = head.lemma_.lower()
    args = [c for c in head.children if c.dep_ in SUBJECT_DEPS | OBJECT_DEPS]
    lemmas = {t.lemma_.lower() for a in args for t in [a, *a.children] if t.dep_ in {"compound", *SUBJECT_DEPS, *OBJECT_DEPS}}
    for category, keywords in EVENT_TYPE_KEYWORDS.items():
        if head_lemma in keywords:
            return category
    for category, keywords in EVENT_TYPE_KEYWORDS.items():
        if lemmas & keywords:
            return category
    return "general"


def extract_event_description(text_or_span):
    root = _head(text_or_span)
    subject = next((c for c in root.children if c.dep_ in SUBJECT_DEPS), None)
    obj = next((c for c in root.children if c.dep_ in OBJECT_DEPS), None)
    parts_found = sum(x is not None for x in (root,subject,obj))
    conf = (parts_found/3)*100
    parts = [str(p) for p in (full_phrase(subject),root,full_phrase(obj)) if p is not None]
    desc = " ".join(parts)
    return (desc,conf)


def _chunk_topic(chunk) -> str:
    # Drop determiners, possessors and the possessive marker itself ("the Bank's committee" -> "committee";
    # news text often uses a curly apostrophe, so "’s" must go too).
    # A token that still ends in a possessive ("Bank‘s", parsed as one token) is a possessor too.
    words = [t.text for t in chunk
             if t.dep_ not in {"det", "poss", "case"} and t.pos_ not in {"PRON", "PART", "PUNCT"}
             and not re.search(r"['’‘]s$", t.text)]
    return " ".join(words).lower().strip()


def extract_topic(text_or_span) -> Topic:
    sent = _first_sentence(text_or_span)
    head = event_head(sent) or sent.root
    chunks = list(sent.noun_chunks)
    entity_tokens = {t.i for ent in sent.ents for t in ent}

    def candidates():
        # Prefer the event verb's object (what happened to), then its subject, then any non-entity noun chunk.
        yield from (c for c in chunks if c.root.dep_ in OBJECT_DEPS and c.root.head == head)
        yield from (c for c in chunks if c.root.dep_ in SUBJECT_DEPS and c.root.head == head)
        yield from (c for c in chunks if c.root.dep_ in OBJECT_DEPS)
        yield from chunks

    for chunk in candidates():
        if chunk.root.i in entity_tokens:
            continue
        name = _chunk_topic(chunk)
        if name:
            return Topic(name=name)
    return Topic(name="general")


def is_event_sentence(sent: Span, min_anchors: int = 1) -> bool:
    head = event_head(sent)
    if head is None or head.pos_ not in {"VERB","AUX"} or len(sent) < 4:
        return False
    # "X is Y" describes a state, not something that happened.
    if head.lemma_.lower() in COPULA_VERBS:
        return False
    subject = next((c for c in head.children if c.dep_ in SUBJECT_DEPS), None)
    if subject is None:
        return False
    named = sum(1 for ent in sent.ents if ent.label_ in LABEL_MAP)
    dates = sum(1 for ent in sent.ents if ent.label_ == "DATE")
    # "I think...", "We know..." with only a date are commentary, not events.
    if subject.pos_ == "PRON" and named == 0:
        return False
    return named + dates >= min_anchors


def _content_lemmas(span) -> set[str]:
    return {t.lemma_.lower() for t in span if t.is_alpha and not t.is_stop}


def salience(sent: Span, position: int, title_lemmas: set[str], event: Event) -> float:
    # Higher = more likely to be the news. Weights are deliberately simple and explainable.
    lemmas = _content_lemmas(sent)
    headline = len(lemmas & title_lemmas) / len(title_lemmas) if title_lemmas else 0.0
    named = min(sum(1 for e in sent.ents if e.label_ in LABEL_MAP), 3) / 3
    return (3.0 * headline
            + 1.0 * (event.date_source == "explicit")
            + 1.0 * named
            + 1.0 * (event.type != "general")
            + 1.0 / (1 + position))


def extract_event(text_or_span, article_date: datetime.date, article_id: str = "") -> Event:
    sent = _first_sentence(text_or_span)
    (desc, conf) = extract_event_description(sent)
    date, date_source = resolve_event_date(sent, article_date)
    event_type = classify_event_type(sent)
    id = get_id(article_id + desc + str(date))
    return Event(id=id, description=desc, date=date, type=event_type, date_source=date_source)


class Extractor(Protocol):
    # Swap point: a fine-tuned NER/event model only has to implement this.
    def extract(self, article: Article, text: str) -> ExtractionResult: ...


class SpacyExtractor:
    def __init__(self, config: ExtractConfig | None = None):
        self.config = config or ExtractConfig()
        self.nlp = get_nlp(self.config.spacy_model)

    def extract(self, article: Article, text: str) -> ExtractionResult:
        doc = self.nlp(text)
        mentions = extract_entities(doc)
        by_name = {e.name.lower(): e for e in mentions}
        title_lemmas = _content_lemmas(self.nlp(article.title)) if article.title else set()
        scored = {}
        for position, sent in enumerate(doc.sents):
            if not is_event_sentence(sent, self.config.min_anchors):
                continue
            event = extract_event(sent, article.date, article.id)
            if event.id in scored:
                continue
            extracted = ExtractedEvent(
                event=event,
                entities=[by_name.get(e.name.lower(), e) for e in extract_entities(sent)],
                topic=extract_topic(sent),
                source_text=sent.text.strip(),
            )
            scored[event.id] = (salience(sent, position, title_lemmas, event), position, extracted)
        # Keep the N most salient events, reported in article order.
        top = sorted(scored.values(), key=lambda x: (-x[0], x[1]))[:self.config.max_events_per_article]
        events = [extracted for _, _, extracted in sorted(top, key=lambda x: x[1])]
        return ExtractionResult(article=article, entities=mentions, events=events)


def extract_article(article: Article, text: str) -> ExtractionResult:
    return SpacyExtractor().extract(article, text)
