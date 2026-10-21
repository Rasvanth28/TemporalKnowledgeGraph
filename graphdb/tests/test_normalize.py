from __future__ import annotations

from graphdb.normalize import normalize_entity_name


def test_normalization_matches_person_a_cases():
    assert normalize_entity_name("The  Bank of England") == "Bank of England"
    assert normalize_entity_name("Britain's") == "Britain"
    assert normalize_entity_name("  The   Federal Reserve  ") == "Federal Reserve"


def test_normalization_is_case_preserving():
    assert normalize_entity_name("the federal reserve") == "federal reserve"
