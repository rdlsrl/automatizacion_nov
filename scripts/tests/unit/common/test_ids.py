from __future__ import annotations

from uuid import UUID

from drilling_knowledge.common.ids import CorrelationId, EntityId, RunId


def test_entity_id_can_be_created_and_rendered() -> None:
    entity_id = EntityId.new()

    assert isinstance(entity_id.as_uuid(), UUID)
    assert str(entity_id) == str(entity_id.as_uuid())


def test_identifier_can_be_parsed_from_string() -> None:
    run_id = RunId.new()
    reparsed = RunId.from_string(str(run_id))

    assert reparsed == run_id


def test_identifier_subtypes_remain_distinct_classes() -> None:
    correlation_id = CorrelationId.new()

    assert isinstance(correlation_id, CorrelationId)
    assert correlation_id.__class__.__name__ == "CorrelationId"
