from pipeline.extract import extract_entities,extract_event_description,extract_event,extract_topic
import datetime


def test_extract_entities():
        text = "The Federal Reserve raised interest rates"
        entities = extract_entities(text)
        names = [e.name for e in entities]
        assert "The Federal Reserve" in names

def test_extract_event_description():
        text = "The Federal Reserve raised interest rates"
        (desc,conf) = extract_event_description(text)
        assert desc == "Federal Reserve raised interest rates"
        assert conf == 100

def test_extract_event():
    text = "The Federal Reserve raised interest rates in March 2026"
    event = extract_event(text,datetime.date(2026,1,1))
    assert event.description == "Federal Reserve raised interest rates"
    assert event.date == datetime.date(2026,3,15)
    assert event.type == "policy_change"

def test_extract_topic():
    text = "The Federal Reserve raised interest rates in March 2026"
    topic = extract_topic(text)
    assert topic.name == "interest rates"

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
