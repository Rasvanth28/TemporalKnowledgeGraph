from __future__ import annotations

import pytest

from graphdb.apply_schema import apply_schema, verify_schema
from graphdb.config import load_neo4j_config
from graphdb.connection import Neo4jClient
from graphdb.health import check_health

pytestmark = pytest.mark.integration

PROBE_ID = "test_person_b_stage1_schema_probe"


def test_health_schema_and_cleanup_round_trip():
    config = load_neo4j_config()
    client = Neo4jClient(config)

    try:
        health = check_health(config, client=client)
        assert health.connected, health.error

        first = apply_schema(client, wait_seconds=30)
        assert first.ok, first.missing

        second = apply_schema(client, wait_seconds=30)
        assert second.ok, second.missing

        verified = verify_schema(client)
        assert verified.ok, verified.missing

        client.run(
            "MERGE (n:TestProbe {id: $id}) "
            "ON CREATE SET n.created_by = 'graphdb-integration-test'",
            {"id": PROBE_ID},
        )
        rows = client.run(
            "MATCH (n:TestProbe {id: $id}) RETURN n.id AS id",
            {"id": PROBE_ID},
        )
        assert rows == [{"id": PROBE_ID}]
    finally:
        try:
            client.run(
                "MATCH (n:TestProbe {id: $id}) DETACH DELETE n",
                {"id": PROBE_ID},
            )
        finally:
            client.close()
