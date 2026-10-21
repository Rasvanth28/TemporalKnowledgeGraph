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


def _all_pairs_reference(results, config=LinkConfig(), existing=()):
    """The original quadratic algorithm, kept here to prove the fast path gives identical links."""
    from pipeline.link import has_content_signal
    new_items = [(r.article.id, e) for r in results for e in r.events]
    new_ids = {e.event.id for _, e in new_items}
    items = sorted(new_items + [(a, e) for a, e in existing if e.event.id not in new_ids],
                   key=lambda item: (item[1].event.date, item[1].event.id))
    scorer = TfidfTopicScorer()
    scorer.fit([e for _, e in items])
    links = []
    for i, (art_a, a) in enumerate(items):
        cands = []
        for art_b, b in items[i + 1:]:
            if (a.event.id not in new_ids and b.event.id not in new_ids) or (art_a == art_b and not config.link_within_article):
                continue
            link = compute_link(a, b, config, scorer)
            if link.confidence >= config.threshold and has_content_signal(link):
                cands.append(link)
        links.extend(sorted(cands, key=lambda lk: (-lk.confidence, lk.to_event_id))[:config.top_k])
    return links


def test_fast_linking_matches_the_all_pairs_algorithm():
    import random
    rng = random.Random(7)
    names = [Entity(id=f"e{i}", name=f"Name {i}", type="ORG") for i in range(12)]
    words = "bank rates inflation oil opec saudi petrol prices cut hold vote election storm coast budget tax mortgage".split()
    events = []
    for i in range(80):
        text = " ".join(rng.sample(words, 4))
        events.append(ev(f"x{i:02d}", datetime.date(2024, 1, 1) + datetime.timedelta(days=rng.randrange(120)),
                         text, rng.choice(words), rng.sample(names, rng.randrange(0, 3))))
    results = [result(f"art{i // 3}", *events[i:i + 3]) for i in range(0, 60, 3)]
    existing = [(f"old{i}", e) for i, e in enumerate(events[60:])]

    def key(links):
        return sorted((lk.from_event_id, lk.to_event_id, lk.confidence, lk.reason) for lk in links)

    for config in (LinkConfig(), LinkConfig(top_k=2), LinkConfig(link_within_article=True, threshold=0.2)):
        fast = link_events(results, config, existing=existing)
        assert fast and key(fast) == key(_all_pairs_reference(results, config, existing))


def test_link_events_tolerates_the_same_event_twice():
    links = link_events([result("a", RATE_1), result("a", RATE_1), result("b", RATE_2)])
    assert [(lk.from_event_id, lk.to_event_id) for lk in links] == [("r1", "r2")]
