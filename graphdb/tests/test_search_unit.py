import datetime as dt

import pytest

from graphdb.search import fuse, interpret, keywords_for, lucene_query, match_entities, parse_dates

TODAY = dt.date(2026, 10, 21)
D = dt.date


@pytest.mark.parametrize("prompt, start, end", [
    ("rates in 2024", D(2024, 1, 1), D(2024, 12, 31)),
    ("what happened in June 2024", D(2024, 6, 1), D(2024, 6, 30)),
    ("Bank of England since March 2024", D(2024, 3, 1), TODAY),
    ("oil before 2023", None, D(2023, 12, 31)),
    ("inflation between June 2024 and Sept 2024", D(2024, 6, 1), D(2024, 9, 30)),
    ("from 2023 to 2024", D(2023, 1, 1), D(2024, 12, 31)),
    ("last 3 months", TODAY - dt.timedelta(days=90), TODAY),
    ("the past week", TODAY - dt.timedelta(days=7), TODAY),
    ("last year", D(2025, 1, 1), D(2025, 12, 31)),
    ("this year", D(2026, 1, 1), TODAY),
    ("Q3 2024 rate decisions", D(2024, 7, 1), D(2024, 9, 30)),
    ("anything in December", D(2025, 12, 1), D(2025, 12, 31)),  # most recent December
    ("in March", D(2026, 3, 1), D(2026, 3, 31)),
])
def test_parse_dates(prompt, start, end):
    got = parse_dates(prompt, TODAY)
    assert (got[0], got[1]) == (start, end)
    assert got[2] and got[2] in prompt.lower()


def test_parse_dates_ignores_words_that_only_look_like_months():
    assert parse_dates("the Fed may cut rates", TODAY) == (None, None, None)
    assert parse_dates("why did the market march higher", TODAY) == (None, None, None)


ENTITIES = [
    {"id": "boe", "name": "Bank of England", "type": "ORG"},
    {"id": "bank", "name": "Bank", "type": "ORG"},
    {"id": "uk", "name": "UK", "type": "LOCATION"},
    {"id": "us", "name": "US", "type": "LOCATION"},
    {"id": "bailey", "name": "Andrew Bailey", "type": "PERSON"},
    {"id": "opec", "name": "Opec", "type": "ORG"},
]


def names(found):
    return [e["name"] for e in found]


def test_match_entities_prefers_the_longest_name():
    assert names(match_entities("what did the bank of england do", ENTITIES)) == ["Bank of England"]


def test_match_entities_tolerates_typos():
    found = match_entities("andrew baily on inflation", ENTITIES)
    assert names(found) == ["Andrew Bailey"] and found[0]["score"] < 100


def test_short_acronyms_need_capitals():
    assert names(match_entities("tell us about UK rates", ENTITIES)) == ["UK"]
    assert names(match_entities("show me uk rates", ENTITIES)) == []


def test_keywords_drop_stopwords_entities_and_dates():
    prompt = "How did the Bank of England change interest rates in 2024?"
    meaning = interpret(prompt, ENTITIES, TODAY)
    assert names(meaning.entities) == ["Bank of England"]
    assert meaning.keywords == ["interest", "rates"]
    assert (meaning.start, meaning.end) == (D(2024, 1, 1), D(2024, 12, 31))
    assert keywords_for("Opec oil output", [ENTITIES[5]], None) == ["oil", "output"]


def test_lucene_query_escapes_operators_and_syntax():
    assert lucene_query(["rates", "AND", "a:b", "(x)"]) == r"rates and a\:b \(x\)"


def test_fuse_rewards_events_found_by_several_retrievers():
    ranked = fuse({"entity": ["a", "b"], "keyword": ["b", "c"], "meaning": ["b", "a"]})
    assert ranked[0][0] == "b"
    assert [event_id for event_id, _ in ranked] == ["b", "a", "c"]


def test_meaning_cutoff_is_relative_to_the_best_match():
    from graphdb.search import meaning_cutoff
    # Scores are Neo4j's rescaled cosine, (1 + cos) / 2.
    # Names/keywords matched: only near-equivalents of the best meaning match survive.
    assert meaning_cutoff([0.87, 0.86, 0.59, 0.56], lexical_hits=True) == pytest.approx(0.79)
    # Meaning alone: a little looser.
    assert meaning_cutoff([0.85, 0.79, 0.75], lexical_hits=False) == pytest.approx(0.73)
    # Never below the floor that separates on-topic from off-topic prompts.
    assert meaning_cutoff([0.65, 0.63], lexical_hits=False) == pytest.approx(0.70)
    assert meaning_cutoff([], lexical_hits=False) == 0.70


def test_keywords_drop_the_text_of_fuzzy_matched_names():
    meaning = interpret("what did Andrew Baily say about inflation", ENTITIES, TODAY)
    assert names(meaning.entities) == ["Andrew Bailey"]
    assert meaning.keywords == ["inflation"]
