import datetime

from common.schema import Article, Entity, Event, Topic, ExtractedEvent, ExtractionResult
from pipeline.config import LinkConfig
from pipeline.link import (compute_link, link_events, get_confidence, get_date_score,
                           TfidfTopicScorer, ExactTopicScorer)

FED = Entity(id="fed", name="Federal Reserve", type="ORG")
US = Entity(id="us", name="United States", type="LOCATION")
OPEC = Entity(id="opec", name="OPEC", type="ORG")


def ev(id, date, text, topic, entities):
    return ExtractedEvent(event=Event(id=id, description=text, date=date, type="general"),
                          entities=entities, topic=Topic(name=topic), source_text=text)


def result(article_id, *events):
    article = Article(id=article_id, title="", date=events[0].event.date, source="", url="")
    return ExtractionResult(article=article, entities=[], events=list(events))


RATE_1 = ev("r1", datetime.date(2026,3,1), "The Federal Reserve raised interest rates", "interest rates", [FED, US])
RATE_2 = ev("r2", datetime.date(2026,3,10), "The Federal Reserve raised interest rates again", "interest rates", [FED])
OIL = ev("o1", datetime.date(2026,9,1), "OPEC cut oil production quotas", "oil production quotas", [OPEC])


def test_compute_link_related_events():
    link = compute_link(RATE_1, RATE_2)
    assert link.confidence > 0.5
    assert "shared_entities" in link.reason
    assert "similar_topic" in link.reason
    assert "date_proximity" in link.reason

def test_compute_link_unrelated_events():
    link = compute_link(RATE_1, OIL)
    assert link.confidence == 0.0
    assert link.reason == "weak_link"

def test_confidence_uses_configured_weights():
    config = LinkConfig(entity_weight=1.0, topic_weight=0.0, date_weight=0.0)
    assert get_confidence(0.5, 1.0, 1.0, config) == 0.5
    assert get_confidence(1.0, 1.0, 1.0) == 1.0

def test_date_score_window():
    d = datetime.date(2026,1,1)
    assert get_date_score(d, d) == 1.0
    assert get_date_score(d, d + datetime.timedelta(days=30)) == 0.0

def test_tfidf_scores_partial_topic_overlap():
    a = ev("a", datetime.date(2026,1,1), "Rates rose", "interest rates", [])
    b = ev("b", datetime.date(2026,1,1), "Rates fell", "rates", [])
    c = ev("c", datetime.date(2026,1,1), "Storm hit", "coast", [])
    scorer = TfidfTopicScorer()
    scorer.fit([a, b, c])
    assert scorer.score(a, b) > 0
    assert scorer.score(a, c) == 0
    assert ExactTopicScorer().score(a, b) == 0

def test_link_events_points_earlier_to_later():
    links = link_events([result("art_b", RATE_2), result("art_a", RATE_1), result("art_c", OIL)])
    assert [(lk.from_event_id, lk.to_event_id) for lk in links] == [("r1", "r2")]

def test_link_events_respects_threshold():
    assert link_events([result("a", RATE_1), result("b", RATE_2)], LinkConfig(threshold=0.99)) == []

def test_link_events_skips_same_article_by_default():
    assert link_events([result("a", RATE_1, RATE_2)]) == []
    assert len(link_events([result("a", RATE_1, RATE_2)], LinkConfig(link_within_article=True))) == 1

def test_link_events_caps_outgoing_links_at_top_k():
    later = [ev(f"later{i}", datetime.date(2026,3,2+i), "The Federal Reserve raised interest rates", "interest rates", [FED])
             for i in range(5)]
    results = [result("first", RATE_1)] + [result(f"art{i}", e) for i, e in enumerate(later)]
    links = link_events(results, LinkConfig(top_k=2))
    assert len([lk for lk in links if lk.from_event_id == "r1"]) == 2

def test_inferred_dates_halve_the_date_score():
    a = ev("a", datetime.date(2026,3,1), "x", "general", [])
    b = ev("b", datetime.date(2026,3,1), "y", "general", [])
    config = LinkConfig(entity_weight=0, topic_weight=0, date_weight=1)
    assert compute_link(a, b, config, ExactTopicScorer()).confidence == 1.0
    b.event.date_source = "inferred"
    assert compute_link(a, b, config, ExactTopicScorer()).confidence == 0.5

def test_date_proximity_alone_never_links():
    a = ev("a", datetime.date(2026,3,1), "Storm hit coast", "coast", [])
    b = ev("b", datetime.date(2026,3,1), "Markets rallied", "markets", [])
    assert link_events([result("x", a), result("y", b)], LinkConfig(date_weight=1, entity_weight=0, topic_weight=0)) == []

def test_link_events_links_new_events_to_existing_ones_only():
    rate_0 = ev("r0", datetime.date(2026,2,25), "The Federal Reserve raised interest rates", "interest rates", [FED])
    existing = [("old_a", rate_0), ("old_b", RATE_1)]
    links = link_events([result("new", RATE_2)], existing=existing)
    pairs = {(lk.from_event_id, lk.to_event_id) for lk in links}
    assert ("r0", "r2") in pairs and ("r1", "r2") in pairs
    assert ("r0", "r1") not in pairs  # both already in the graph: linked by an earlier run

def test_link_events_ignores_existing_copies_of_new_events():
    links = link_events([result("a", RATE_1), result("b", RATE_2)], existing=[("a", RATE_1)])
    assert [(lk.from_event_id, lk.to_event_id) for lk in links] == [("r1", "r2")]
