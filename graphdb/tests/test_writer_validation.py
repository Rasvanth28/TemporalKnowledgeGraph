from __future__ import annotations

import pytest

from common.schema import EventLink
from graphdb.writer import (
    PipelineWriter,
    WriterValidationError,
    load_pipeline_output,
)
from graphdb.tests.test_writer_plan import FIXTURE, base_output


class Sentinel(Exception):
    """Raised by the fake client to prove the writer reached the write phase."""


class FakeWriterClient:
    def __init__(self, existing_event_ids: set[str] | None = None):
        self.existing_event_ids = set(existing_event_ids or set())
        self.queries: list[str] = []
        self.writes = 0

    def run(self, query: str, parameters=None, database=None):
        self.queries.append(query)
        if "MATCH (e:Event {id: id})" in query:
            return [
                {"id": event_id}
                for event_id in parameters["ids"]
                if event_id in self.existing_event_ids
            ]
        raise AssertionError(f"unexpected query in validation test: {query}")

    def execute_write(self, work):
        self.writes += 1
        raise Sentinel()


def output_with_external_link() -> object:
    return base_output(
        links=(
            EventLink(
                from_event_id="test_unit_evt_1",
                to_event_id="test_unit_evt_2",
                confidence=0.5,
                reason="unit",
            ),
        )
    )


def test_missing_external_link_endpoint_fails_before_writing():
    client = FakeWriterClient()

    with pytest.raises(WriterValidationError, match="not found in the batch or the database"):
        PipelineWriter(client).write(output_with_external_link())

    assert client.writes == 0


def test_external_link_endpoint_in_database_is_accepted():
    client = FakeWriterClient(existing_event_ids={"test_unit_evt_2"})

    with pytest.raises(Sentinel):
        PipelineWriter(client).write(output_with_external_link())

    assert client.writes == 1
    assert any("MATCH (e:Event {id: id})" in query for query in client.queries)


def test_batch_local_link_endpoints_need_no_database_lookup():
    client = FakeWriterClient()
    output = load_pipeline_output(FIXTURE)

    with pytest.raises(Sentinel):
        PipelineWriter(client).write(output)

    assert client.writes == 1
    assert client.queries == []
