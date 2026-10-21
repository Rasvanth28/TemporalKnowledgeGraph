from pipeline.extract import (extract_entities,extract_event_description,extract_event,extract_topic,
                              parse_date,classify_event_type,normalize_name,SpacyExtractor)
from common.schema import Article
import datetime


def make_article(id="art_test", date=datetime.date(2026,1,1)):
    return Article(id=id,title="t",date=date,source="s",url="u")


def test_extract_entities():
        text = "The Federal Reserve raised interest rates"
        entities = extract_entities(text)
        names = [e.name for e in entities]
        assert "Federal Reserve" in names

def test_entity_names_are_normalized_to_one_id():
    a = extract_entities("The Federal Reserve raised interest rates")
    b = extract_entities("Federal Reserve officials met on Tuesday")
    ids_a = {e.id for e in a if e.name == "Federal Reserve"}
    ids_b = {e.id for e in b if e.name == "Federal Reserve"}
    assert ids_a and ids_a == ids_b

def test_normalize_name():
    assert normalize_name("The  Bank of England") == "Bank of England"
    assert normalize_name("Britain's") == "Britain"

def test_extract_event_description():
        text = "The Federal Reserve raised interest rates"
        (desc,conf) = extract_event_description(text)
        assert desc == "Federal Reserve raised interest rates"
        assert conf == 100

def test_extract_event():
    text = "The Federal Reserve raised interest rates in March 2026"
    event = extract_event(text,datetime.date(2026,1,1))
    assert event.description == "Federal Reserve raised interest rates"
    assert event.date == datetime.date(2026,3,1)
    assert event.type == "policy_change"

def test_event_id_is_deterministic():
    text = "The Federal Reserve raised interest rates in March 2026"
    a = extract_event(text,datetime.date(2026,1,1),"art_1")
    b = extract_event(text,datetime.date(2026,1,1),"art_1")
    assert a.id == b.id

def test_extract_topic():
    text = "The Federal Reserve raised interest rates in March 2026"
    topic = extract_topic(text)
    assert topic.name == "interest rates"

def test_extract_topic_strips_determiner():
    topic = extract_topic("A storm hit the coast")
    assert topic.name == "coast"

def test_extract_entities_finds_policy_keyword():
    text = "The government announced a new access control policy"
    entities = extract_entities(text)
    names = [e.name for e in entities]
    types = [e.type for e in entities]
    assert "access control" in names
    assert "POLICY" in types

def test_extract_entities_find_law_as_policy():
    text = "Congress passed the Affordable Care Act in 2010"
    entities = extract_entities(text)
    policy_entities = [e for e in entities if e.type == "POLICY"]
    assert len(policy_entities) == 1

def test_parse_date_month_without_year_uses_article_year():
    assert parse_date("March", datetime.date(2024,6,1)) == datetime.date(2024,3,1)

def test_parse_date_rejects_unresolvable_mentions():
    assert parse_date("last quarter", datetime.date(2024,6,1)) is None
    assert parse_date("Tuesday", datetime.date(2024,6,1)) is None

def test_parse_date_relative():
    assert parse_date("yesterday", datetime.date(2024,6,1)) == datetime.date(2024,5,31)

def test_classify_event_type_uses_lemmas():
    assert classify_event_type("Voters elected a new parliament in May 2024") == "election"
    assert classify_event_type("The two countries signed a treaty in 2023") == "agreement"
    assert classify_event_type("The cat sat on the mat") == "general"

def test_extractor_makes_one_event_per_qualifying_sentence():
    text = ("The Bank of England raised interest rates in March 2024. "
            "This is important. "
            "Inflation in Britain fell in June 2024.")
    result = SpacyExtractor().extract(make_article(date=datetime.date(2024,7,1)), text)
    dates = sorted(e.event.date for e in result.events)
    assert dates == [datetime.date(2024,3,1), datetime.date(2024,6,1)]
    assert all(e.source_text for e in result.events)

def test_extractor_article_mentions_cover_event_entities():
    text = "The Bank of England raised interest rates in March 2024. Inflation in Britain fell in June 2024."
    result = SpacyExtractor().extract(make_article(), text)
    mention_ids = {e.id for e in result.entities}
    for ev in result.events:
        assert {e.id for e in ev.entities} <= mention_ids

def test_extractor_falls_back_to_article_date():
    article = make_article(date=datetime.date(2025,2,14))
    result = SpacyExtractor().extract(article, "Labour leader Keir Starmer criticised the policy on Tuesday.")
    assert [e.event.date for e in result.events] == [datetime.date(2025,2,14)]

def test_extractor_drops_first_person_commentary():
    result = SpacyExtractor().extract(make_article(), "I think this matters a lot in 2024.")
    assert result.events == []

def test_article_mentions_have_unique_names():
    text = "Birnie wrote a paper in 2023. Birnie updated the figures in 2024."
    result = SpacyExtractor().extract(make_article(date=datetime.date(2024,5,1)), text)
    names = [e.name.lower() for e in result.entities]
    assert len(names) == len(set(names))

def test_parse_date_current_month_resolves_to_article_date():
    assert parse_date("March 2024", datetime.date(2024,3,15)) == datetime.date(2024,3,15)
    assert parse_date("March 2024", datetime.date(2024,5,15)) == datetime.date(2024,3,1)
    assert parse_date("20 March 2024", datetime.date(2024,3,25)) == datetime.date(2024,3,20)
    assert parse_date("2019", datetime.date(2024,3,25)) == datetime.date(2019,1,1)

def test_classify_event_type_ignores_side_clauses():
    assert classify_event_type("Storms hit Japan on 20 March 2024, cutting power to Tokyo.") == "general"

def test_event_description_uses_full_entity_name():
    (desc, _) = extract_event_description("The Bank of England raised interest rates")
    assert desc == "Bank of England raised interest rates"

def test_reporting_verb_uses_reported_clause():
    (desc, _) = extract_event_description("Andrew Bailey said the Bank of England would cut interest rates.")
    assert desc == "Bank of England cut interest rates"
    assert classify_event_type("Andrew Bailey said the Bank of England would cut interest rates.") == "policy_change"

def test_bare_reporting_and_copula_sentences_are_not_events():
    result = SpacyExtractor().extract(make_article(), "Andrew Bailey said so on Tuesday. The Bank of England is an institution in London.")
    assert result.events == []

def test_date_source_marks_explicit_and_inferred():
    article = make_article(date=datetime.date(2025,2,14))
    explicit = extract_event("The Bank of England cut interest rates in March 2024.", article.date)
    inferred = extract_event("The Bank of England cut interest rates.", article.date)
    assert explicit.date_source == "explicit"
    assert (inferred.date, inferred.date_source) == (article.date, "inferred")

def test_extractor_caps_events_and_prefers_headline_sentences():
    from pipeline.config import ExtractConfig
    filler = " ".join(f"Officials in London met analysts from Goldman Sachs in {m} 2024." for m in ["January","February","April"])
    text = filler + " The Bank of England cut interest rates in March 2024."
    article = Article(id="a", title="Bank of England cuts interest rates", date=datetime.date(2024,3,21), source="", url="")
    result = SpacyExtractor(ExtractConfig(max_events_per_article=1)).extract(article, text)
    assert [e.event.description for e in result.events] == ["Bank of England cut interest rates"]

def test_extract_topic_drops_possessive_markers():
    assert extract_topic("The Bank’s monetary policy committee voted to cut rates in August 2024").name == "monetary policy committee"
    assert extract_topic("The Bank‘s monetary policy committee voted to cut rates in August 2024").name == "monetary policy committee"
    assert "’s" not in extract_topic("Last week’s budget has made life more complicated for the Bank of England.").name
    assert "'s" not in extract_topic("Last week's budget made life harder for the Bank of England.").name
