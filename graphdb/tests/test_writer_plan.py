from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from common.schema import (
    Article,
    Entity,
    Event,
    EventLink,
    ExtractedEvent,
    ExtractionResult,
    PipelineOutput,
    Topic,
)
from graphdb.writer import (
    WriterValidationError,
    build_write_plan,
    load_pipeline_output,
    precedes_pairs,
    pipeline_output_from_mapping,
)

FIXTURE = Path(__file__).parent / "fixtures" / "pipeline_output.json"


def fixture_output() -> PipelineOutput:
    return load_pipeline_output(FIXTURE)


def base_output(
    event_id: str = "test_unit_evt_1",
    article_id: str = "test_unit_art_1",
    entity_id: str = "test_unit_ent_1",
    topic: str = "test-unit topic",
    links: tuple[EventLink, ...] = (),
) -> PipelineOutput:
    article = Article(
        id=article_id,
        title="unit",
        date=dt.date(2026, 1, 1),
        source="unit",
        url="https://example.invalid/unit",
    )
    entity = Entity(id=entity_id, name="Unit Entity", type="ORG")
    event = Event(
        id=event_id,
        description="Unit event happened",
        date=dt.date(2026, 1, 2),
        type="general",
        date_source="explicit",
    )


    extracted = ExtractedEvent(
        event=event,
        entities=[entity],
        topic=Topic(name=topic),
        source_text="Unit event happened.",
    )
    return PipelineOutput(
        results=[ExtractionResult(article=article, entities=[entity], events=[extracted])],
        links=list(links),
    )


def test_fixture_plan_has_expected_shape():
    plan = build_write_plan(fixture_output())

    assert plan.node_count == 12
    assert plan.relationship_count == 26
    assert len(plan.articles) == 3
    assert len(plan.events) == 4
    assert len(plan.entities) == 3
    assert len(plan.topics) == 2
    assert len(plan.linked_to) == 4
    assert len(plan.article_about) == 3


def test_fixture_repeated_entities_are_deduplicated():
    plan = build_write_plan(fixture_output())
    entity_ids = [row["id"] for row in plan.entities]

    assert entity_ids.count("test_fixture_ent_bank") == 1
    assert sorted(entity_ids) == [
        "test_fixture_ent_bank",
        "test_fixture_ent_committee",
        "test_fixture_ent_stats",
    ]


def test_fixture_article_about_is_derived_from_event_topics():
    plan = build_write_plan(fixture_output())
    about = {(row["article_id"], row["topic_name"]) for row in plan.article_about}

    assert ("test_fixture_art_1", "test-fixture interest rates") in about
    assert ("test_fixture_art_2", "test-fixture inflation") in about
    assert ("test_fixture_art_3", "test-fixture interest rates") in about


def test_precedes_pairs_follow_global_date_then_id_order():
    events = [
        {"id": "b", "date": "2026-03-01"},
        {"id": "a", "date": "2026-01-01"},
        {"id": "c", "date": "2026-03-01"},
    ]

    assert precedes_pairs(events) == [("a", "b"), ("b", "c")]


def test_precedes_pairs_handles_single_event():
    assert precedes_pairs([{"id": "a", "date": "2026-01-01"}]) == []


def test_duplicate_event_id_is_rejected():
    output = base_output()
    duplicate = base_output(event_id="test_unit_evt_1", article_id="test_unit_art_2")
    output.results.extend(duplicate.results)

    with pytest.raises(WriterValidationError, match="duplicate Event id"):
        build_write_plan(output)


def test_event_entity_must_be_mentioned_by_article():
    output = base_output()
    output.results[0].entities = []

    with pytest.raises(WriterValidationError, match="does not mention"):
        build_write_plan(output)


def test_self_link_is_rejected():
    output = base_output(
        links=(
            EventLink(
                from_event_id="test_unit_evt_1",
                to_event_id="test_unit_evt_1",
                confidence=0.5,
                reason="self",
            ),
        )
    )

    with pytest.raises(WriterValidationError, match="self-link"):
        build_write_plan(output)


def test_duplicate_links_keep_the_highest_confidence():
    output = base_output(
        links=(
            EventLink("test_unit_evt_1", "test_unit_evt_2", 0.2, "low"),
            EventLink("test_unit_evt_1", "test_unit_evt_2", 0.8, "high"),
        )
    )

    plan = build_write_plan(output)

    assert len(plan.linked_to) == 1
    assert plan.linked_to[0]["confidence"] == 0.8
    assert plan.linked_to[0]["reason"] == "high"


def test_confidence_out_of_range_is_rejected():
    with pytest.raises(WriterValidationError, match="between 0.0 and 1.0"):
        pipeline_output_from_mapping(
            {
                "results": [],
                "links": [
                    {
                        "from_event_id": "a",
                        "to_event_id": "b",
                        "confidence": 2.0,
                        "reason": "bad",
                    }
                ],
            }
        )


def test_bad_iso_date_is_rejected():
    data = {
        "results": [
            {
                "article": {
                    "id": "a",
                    "title": "t",
                    "date": "not-a-date",
                    "source": "",
                    "url": "",
                },
                "entities": [],
                "events": [],
            }
        ],
        "links": [],
    }

    with pytest.raises(WriterValidationError, match="ISO date"):
        pipeline_output_from_mapping(data)
