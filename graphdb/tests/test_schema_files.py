from __future__ import annotations

from graphdb.apply_schema import (
    CONSTRAINTS_FILE,
    INDEXES_FILE,
    read_statements,
)

EXPECTED_INDEXES = [
    "CREATE INDEX event_date  IF NOT EXISTS FOR (e:Event)  ON (e.date)",
    "CREATE INDEX event_type  IF NOT EXISTS FOR (e:Event)  ON (e.type)",
    "CREATE INDEX entity_name IF NOT EXISTS FOR (n:Entity) ON (n.name)",
    "CREATE INDEX topic_name  IF NOT EXISTS FOR (t:Topic)  ON (t.name)",
]

EXPECTED_CONSTRAINTS = [
    "CREATE CONSTRAINT article_id_unique IF NOT EXISTS FOR (a:Article) REQUIRE a.id IS UNIQUE",
    "CREATE CONSTRAINT event_id_unique   IF NOT EXISTS FOR (e:Event)   REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT entity_id_unique  IF NOT EXISTS FOR (n:Entity)  REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT topic_name_unique IF NOT EXISTS FOR (t:Topic)   REQUIRE t.name IS UNIQUE",
]


def test_index_statements_match_design_document_exactly():
    assert read_statements(INDEXES_FILE) == EXPECTED_INDEXES


def test_constraint_statements_match_approved_constraints():
    assert read_statements(CONSTRAINTS_FILE) == EXPECTED_CONSTRAINTS
