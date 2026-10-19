from __future__ import annotations

from typing import Any

import pytest

from graphdb.apply_schema import (
    SHOW_CONSTRAINTS_QUERY,
    SHOW_INDEXES_QUERY,
    SchemaApplicationError,
    apply_schema,
    verify_schema,
)


class EquivalentIndexError(Exception):
    code = "Neo.ClientError.Schema.EquivalentSchemaRuleAlreadyExists"


def make_indexes(include_topic_name: bool = True) -> list[dict[str, Any]]:
    rows = [
        {
            "name": "event_date",
            "type": "RANGE",
            "entityType": "NODE",
            "labelsOrTypes": ["Event"],
            "properties": ["date"],
            "owningConstraint": None,
            "state": "ONLINE",
        },
        {
            "name": "event_type",
            "type": "RANGE",
            "entityType": "NODE",
            "labelsOrTypes": ["Event"],
            "properties": ["type"],
            "owningConstraint": None,
            "state": "ONLINE",
        },
        {
            "name": "entity_name",
            "type": "RANGE",
            "entityType": "NODE",
            "labelsOrTypes": ["Entity"],
            "properties": ["name"],
            "owningConstraint": None,
            "state": "ONLINE",
        },
    ]
    if include_topic_name:
        rows.append(
            {
                "name": "topic_name",
                "type": "RANGE",
                "entityType": "NODE",
                "labelsOrTypes": ["Topic"],
                "properties": ["name"],
                "owningConstraint": None,
                "state": "ONLINE",
            }
        )
    else:
        rows.append(
            {
                "name": "constraint_topic_name_unique",
                "type": "RANGE",
                "entityType": "NODE",
                "labelsOrTypes": ["Topic"],
                "properties": ["name"],
                "owningConstraint": "topic_name_unique",
                "state": "ONLINE",
            }
        )
    return rows


def make_constraints() -> list[dict[str, Any]]:
    return [
        {
            "name": "article_id_unique",
            "type": "UNIQUENESS",
            "entityType": "NODE",
            "labelsOrTypes": ["Article"],
            "properties": ["id"],
        },
        {
            "name": "event_id_unique",
            "type": "UNIQUENESS",
            "entityType": "NODE",
            "labelsOrTypes": ["Event"],
            "properties": ["id"],
        },
        {
            "name": "entity_id_unique",
            "type": "UNIQUENESS",
            "entityType": "NODE",
            "labelsOrTypes": ["Entity"],
            "properties": ["id"],
        },
        {
            "name": "topic_name_unique",
            "type": "UNIQUENESS",
            "entityType": "NODE",
            "labelsOrTypes": ["Topic"],
            "properties": ["name"],
        },
    ]


class FakeSchemaClient:
    def __init__(
        self,
        indexes: list[dict[str, Any]],
        constraints: list[dict[str, Any]],
        equivalent_topic_index: bool = False,
    ):
        self.indexes = indexes
        self.constraints = constraints
        self.equivalent_topic_index = equivalent_topic_index
        self.queries: list[str] = []

    def run(self, query: str, parameters=None, database=None):
        self.queries.append(query)
        if query == SHOW_INDEXES_QUERY:
            return self.indexes
        if query == SHOW_CONSTRAINTS_QUERY:
            return self.constraints
        if self.equivalent_topic_index and query.startswith("CREATE INDEX topic_name"):
            raise EquivalentIndexError("Equivalent index already exists")
        return []

    @property
    def ddl_queries(self) -> list[str]:
        return [query for query in self.queries if query.startswith("CREATE ")]


def test_apply_schema_is_rerunnable_and_verifies_all_coverage():
    client = FakeSchemaClient(make_indexes(), make_constraints())

    first = apply_schema(client, wait_seconds=0)
    second = apply_schema(client, wait_seconds=0)

    assert first.ok is True
    assert second.ok is True
    assert len(first.index_checks) == 4
    assert len(first.constraint_checks) == 4
    assert all(check.exact for check in first.index_checks)
    assert all(check.exact for check in first.constraint_checks)
    assert len(client.ddl_queries) == 16


def test_equivalent_topic_index_is_verified_instead_of_hidden():
    client = FakeSchemaClient(
        make_indexes(include_topic_name=False),
        make_constraints(),
        equivalent_topic_index=True,
    )

    report = apply_schema(client, wait_seconds=0)

    assert report.ok is True
    topic_check = next(
        check for check in report.index_checks if check.required_name == "topic_name"
    )
    assert topic_check.exact is False
    assert topic_check.satisfied_by == "constraint_topic_name_unique"
    assert len(report.equivalent_conflicts) == 1


def test_missing_index_coverage_fails_with_a_report():
    indexes = [item for item in make_indexes() if item["name"] != "entity_name"]
    client = FakeSchemaClient(indexes, make_constraints())

    with pytest.raises(SchemaApplicationError) as excinfo:
        apply_schema(client, wait_seconds=0)

    report = excinfo.value.report
    assert report is not None
    assert any(
        check.label == "Entity" and check.property == "name" and not check.ok
        for check in report.index_checks
    )


def test_verify_schema_does_not_apply_ddl():
    client = FakeSchemaClient(make_indexes(), make_constraints())

    report = verify_schema(client)

    assert report.ok is True
    assert client.ddl_queries == []
    assert all(query in {SHOW_INDEXES_QUERY, SHOW_CONSTRAINTS_QUERY} for query in client.queries)
