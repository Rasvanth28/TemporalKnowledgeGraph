import datetime
from typing import Protocol

from sklearn.feature_extraction.text import TfidfVectorizer

from common.schema import Entity, EventLink, ExtractedEvent, ExtractionResult
from pipeline.config import LinkConfig


class TopicScorer(Protocol):
    # Swap point: an embedding-based scorer only has to implement fit + score.
    def fit(self, events: list[ExtractedEvent]) -> None: ...
    def score(self, a: ExtractedEvent, b: ExtractedEvent) -> float: ...


class ExactTopicScorer:
    def fit(self, events: list[ExtractedEvent]) -> None:
        pass

    def score(self, a: ExtractedEvent, b: ExtractedEvent) -> float:
        if a.topic.name == "general" or b.topic.name == "general":
            return 0.0
        return 1.0 if a.topic.name == b.topic.name else 0.0


class TfidfTopicScorer:
    # Cosine similarity of TF-IDF vectors over "topic + source sentence".
    # Fit once over the whole corpus so IDF reflects which words are actually distinctive.
    def __init__(self):
        self.index = {}
        self.matrix = None

    @staticmethod
    def _text(e: ExtractedEvent) -> str:
        topic = "" if e.topic.name == "general" else e.topic.name
        return f"{topic} {e.source_text or e.event.description}"

    def fit(self, events: list[ExtractedEvent]) -> None:
        self.index = {e.event.id: i for i, e in enumerate(events)}
        texts = [self._text(e) for e in events]
        if not any(t.strip() for t in texts):
            self.matrix = None
            return
        vectorizer = TfidfVectorizer(stop_words="english", sublinear_tf=True)
        try:
            self.matrix = vectorizer.fit_transform(texts)
        except ValueError:  # every word was a stop word
            self.matrix = None

    def score(self, a: ExtractedEvent, b: ExtractedEvent) -> float:
        if self.matrix is None or a.event.id not in self.index or b.event.id not in self.index:
            return 0.0
        # Rows are L2-normalised by TfidfVectorizer, so the dot product is the cosine.
        va = self.matrix[self.index[a.event.id]]
        vb = self.matrix[self.index[b.event.id]]
        return float(va.multiply(vb).sum())


def get_jaccard_score(a : list[Entity] , b : list[Entity]) -> float:
    ids_a = {e.id for e in a}
    ids_b = {e.id for e in b}
    union = ids_a | ids_b
    if not union:
        return 0.0
    return len(ids_a & ids_b)/len(union)


def get_date_score(a: datetime.date, b:datetime.date,window_days: int = 30) -> float:
    days_apart = abs((a-b).days)
    if days_apart >= window_days:
        return 0.0
    return 1.0 - (days_apart/window_days)


def get_confidence(jaccard_score:float,topic_score:float,date_score:float,config: LinkConfig = LinkConfig()) -> float:
    total = config.entity_weight + config.topic_weight + config.date_weight
    if total <= 0:
        return 0.0
    weighted = (config.entity_weight*jaccard_score + config.topic_weight*topic_score + config.date_weight*date_score)
    return round(weighted/total, 4)


TOPIC_SIGNAL = 0.2


def has_content_signal(link: EventLink) -> bool:
    # Being close in time is not a relationship on its own.
    return "shared_entities" in link.reason or "similar_topic" in link.reason


def get_reason(jaccard_score : float,topic_score: float, date_score :float) -> str:
    reasons = []
    if jaccard_score > 0:
        reasons.append("shared_entities")
    if topic_score >= TOPIC_SIGNAL:
        reasons.append("similar_topic")
    if date_score > 0.5:
        reasons.append("date_proximity")
    return "+".join(reasons) if reasons else "weak_link"


def compute_link(a: ExtractedEvent, b: ExtractedEvent, config: LinkConfig = LinkConfig(), scorer: TopicScorer | None = None) -> EventLink:
    if scorer is None:
        scorer = TfidfTopicScorer()
        scorer.fit([a, b])
    jaccard_score = get_jaccard_score(a.entities,b.entities)
    topic_score = scorer.score(a, b)
    date_score = get_date_score(a.event.date,b.event.date,config.date_window_days)
    if "inferred" in (a.event.date_source, b.event.date_source):
        date_score *= config.inferred_date_factor
    return EventLink(
        from_event_id=a.event.id,
        to_event_id=b.event.id,
        confidence=get_confidence(jaccard_score,topic_score,date_score,config),
        reason=get_reason(jaccard_score,topic_score,date_score),
    )


def link_events(results: list[ExtractionResult], config: LinkConfig = LinkConfig(), scorer: TopicScorer | None = None,
                existing: list[tuple[str, ExtractedEvent]] = ()) -> list[EventLink]:
    # Links always point earlier -> later (ties broken by id), so they can become PRECEDES edges.
    # existing: (article_id, event) already in the graph. They are scored against the new events
    # but never against each other, because an earlier run already linked those pairs.
    # O(n^2) over events: fine for thousands of events; callers bound `existing` by a date window.
    new_items = [(r.article.id, e) for r in results for e in r.events]
    new_ids = {e.event.id for _, e in new_items}
    items = new_items + [(a, e) for a, e in existing if e.event.id not in new_ids]
    items.sort(key=lambda item: (item[1].event.date, item[1].event.id))
    scorer = scorer or TfidfTopicScorer()
    scorer.fit([e for _, e in items])

    links = []
    for i, (article_a, a) in enumerate(items):
        candidates = []
        for article_b, b in items[i+1:]:
            if a.event.id not in new_ids and b.event.id not in new_ids:
                continue
            if article_a == article_b and not config.link_within_article:
                continue
            link = compute_link(a, b, config, scorer)
            if link.confidence >= config.threshold and has_content_signal(link):
                candidates.append(link)
        candidates.sort(key=lambda link: (-link.confidence, link.to_event_id))
        links.extend(candidates[:config.top_k])
    return links
