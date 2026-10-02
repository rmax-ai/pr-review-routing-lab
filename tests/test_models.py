import pytest
from pydantic import ValidationError

from review_lab.models import Finding, QuestionAnswer, StageRecord


def test_strict_model_round_trip():
    finding = Finding.model_validate_json(
        '{"id":"F1","severity":"blocker","defect_class":"other","evidence":"x","confidence":0.9}'
    )
    assert Finding.model_validate_json(finding.model_dump_json()) == finding


def test_unknown_fields_rejected():
    with pytest.raises(ValidationError):
        Finding.model_validate_json(
            '{"id":"F1","severity":"minor","defect_class":"other","evidence":"x",'
            '"confidence":0,"unexpected":1}'
        )


def test_boolean_probability_conflict_is_rejected():
    with pytest.raises(ValidationError):
        QuestionAnswer.model_validate(
            {
                "id": "q",
                "type": "boolean",
                "value": False,
                "probabilities": {"true": 0.9, "false": 0.1},
            }
        )


def test_stage_timestamps_are_iso8601():
    with pytest.raises(ValidationError):
        StageRecord(
            name="stage",
            started_at="not-a-time",
            ended_at="2025-01-01T00:00:00+00:00",
            duration_ms=0,
        )
