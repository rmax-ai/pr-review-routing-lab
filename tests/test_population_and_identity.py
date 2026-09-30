import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from review_lab.gates.jev import JevAdapter
from review_lab.metrics import benchmark_metrics
from review_lab.models import DataSource, ReviewCase, Route, RunRecord, Terminal, UsageCost
from review_lab.question_sets import CANONICAL_QUESTION_IDS
from review_lab.runner import Runner, _run_seed
from review_lab.util import BoundedProcessResult, now


def _jev_envelope(identity: dict[str, str] | None = None) -> dict[str, object]:
    answer = {
        "id": "needs_semantic_reasoning_beyond_evidence",
        "type": "boolean",
        "value": False,
        "probabilities": {"true": 0.0, "false": 1.0},
        "derived_confidence": 1.0,
    }
    return {"ok": True, "answers": [answer], "usage": {}, **(identity or {})}


def test_live_jev_requires_the_identity_triplet_but_simulated_does_not():
    identity = {
        "case_digest": "a" * 64,
        "head_digest": "b" * 64,
        "packet_digest": "c" * 64,
    }
    strict = JevAdapter._validate_envelope(
        _jev_envelope(), {"needs_semantic_reasoning_beyond_evidence": "boolean"},
        DataSource.measured, 0.0, identity
    )
    assert strict.error == "jev_audit_partial"

    accepted = JevAdapter._validate_envelope(
        _jev_envelope(),
        {"needs_semantic_reasoning_beyond_evidence": "boolean"},
        DataSource.simulated,
        0.0,
        identity,
    )
    assert accepted.error is None
    mismatch = JevAdapter._validate_envelope(
        _jev_envelope({"case_digest": "wrong"}),
        {"needs_semantic_reasoning_beyond_evidence": "boolean"},
        DataSource.simulated,
        0.0,
        identity,
    )
    assert mismatch.error == "jev_audit_partial"

    correct = JevAdapter._validate_envelope(
        _jev_envelope(identity),
        {"needs_semantic_reasoning_beyond_evidence": "boolean"},
        DataSource.measured,
        0.0,
        identity,
    )
    assert correct.error is None
    wrong_digest = dict(identity, head_digest="d" * 64)
    wrong = JevAdapter._validate_envelope(
        _jev_envelope(identity),
        {"needs_semantic_reasoning_beyond_evidence": "boolean"},
        DataSource.measured,
        0.0,
        wrong_digest,
    )
    assert wrong.error == "jev_audit_partial"
    missing_state_digest = dict(identity)
    missing_state_digest.pop("packet_digest")
    missing_state = JevAdapter._validate_envelope(
        _jev_envelope(identity),
        {"needs_semantic_reasoning_beyond_evidence": "boolean"},
        DataSource.measured,
        0.0,
        missing_state_digest,
    )
    assert missing_state.error == "jev_audit_partial"


def test_live_jev_process_enforces_identity_triplet(tmp_path, monkeypatch):
    from review_lab.gates import jev as jev_module

    identity = {
        "case_digest": "a" * 64,
        "head_digest": "b" * 64,
        "packet_digest": "c" * 64,
    }
    answer = {
        "type": "boolean",
        "value": False,
        "probabilities": {"true": 0.0, "false": 1.0},
        "derived_confidence": 1.0,
    }
    payload = {
        "value": {
            "ok": True,
            "answers": [
                {"id": question, **answer}
                for question in sorted(CANONICAL_QUESTION_IDS["gate_a"])
            ],
            "usage": {},
        }
    }

    class FakeProcess:
        pid = 1
        returncode = 0

        def poll(self):
            return self.returncode

    monkeypatch.setenv("REVIEW_LAB_JEV_BIN", "fake-jev")
    monkeypatch.setattr(jev_module.shutil, "which", lambda _: "/bin/fake-jev")
    monkeypatch.setattr(jev_module.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(
        jev_module,
        "communicate_bounded",
        lambda *args, **kwargs: BoundedProcessResult(
            json.dumps(payload["value"]).encode(), b"", False, False
        ),
    )

    adapter = JevAdapter(packet_workdir=tmp_path)
    missing = adapter.evaluate("live", "gate_a", identity, {}, "missing")
    assert missing.error == "jev_audit_partial"

    payload["value"] = {
        **payload["value"],
        **identity,
    }
    accepted = adapter.evaluate("live", "gate_a", identity, {}, "accepted")
    assert accepted.error is None
    assert accepted.answers

    payload["value"] = {**payload["value"], "head_digest": "d" * 64}
    mismatch = adapter.evaluate("live", "gate_a", identity, {}, "mismatch")
    assert mismatch.error == "jev_audit_partial"

    missing_state = dict(identity)
    missing_state.pop("packet_digest")
    payload["value"] = {**payload["value"], **identity}
    state_error = adapter.evaluate("live", "gate_a", missing_state, {}, "state-missing")
    assert state_error.error == "jev_audit_partial"


def _record(
    *,
    usage: list[UsageCost],
    stages: list[dict[str, object]] | None = None,
    sol_invoked: bool = True,
):
    from review_lab.models import StageRecord

    timestamp = now().isoformat()
    return RunRecord(
        run_id="probe",
        case_ref="a" * 12,
        case_id="probe",
        case_digest="a" * 64,
        architecture="A4",
        route=Route.accept,
        terminal=Terminal.sol_complete_accept,
        escalated=False,
        sol_invoked=sol_invoked,
        jev_calls=1,
        remediation_loops=0,
        config_digest="b" * 64,
        backend="live",
        usage=usage,
        stages=[
            StageRecord(
                name=str(item["name"]),
                started_at=timestamp,
                ended_at=timestamp,
                duration_ms=0,
                data={},
            )
            for item in (stages or [])
        ],
    )


def test_aggregate_scores_use_persisted_counts_and_measured_cost_denominators():
    rows = [
        {
            "source": "measured",
            "blocker_recall": 0.0,
            "blocker_recall_numerator": 0,
            "blocker_recall_denominator": 10,
            "material_recall_only": 0.0,
            "material_recall_only_numerator": 0,
            "material_recall_only_denominator": 3,
            "material_recall_including_blocker": 0.25,
            "material_recall_including_blocker_numerator": 1,
            "material_recall_including_blocker_denominator": 4,
            "requirement_coverage_recall": 1.0,
            "requirement_coverage_recall_numerator": 1,
            "requirement_coverage_recall_denominator": 1,
            "required_but_unmentioned": 0,
            "spurious_blocker_rate": 0.0,
            "severity_exactness_rate": 1.0,
            "overcall_rate": 0.0,
        },
        {
            "source": "measured",
            "blocker_recall": 1.0,
            "blocker_recall_numerator": 1,
            "blocker_recall_denominator": 1,
            "material_recall_only": 1.0,
            "material_recall_only_numerator": 2,
            "material_recall_only_denominator": 2,
            "material_recall_including_blocker": 0.2,
            "material_recall_including_blocker_numerator": 2,
            "material_recall_including_blocker_denominator": 10,
            "requirement_coverage_recall": 0.0,
            "requirement_coverage_recall_numerator": 0,
            "requirement_coverage_recall_denominator": 2,
            "required_but_unmentioned": 0,
            "spurious_blocker_rate": 0.0,
            "severity_exactness_rate": 1.0,
            "overcall_rate": 0.0,
        },
    ]
    metrics = {
        row["id"]: row
        for row in benchmark_metrics(
            [], score_rows=rows
        )
    }
    assert metrics["blocker_recall"]["numerator_value"] == 1
    assert metrics["blocker_recall"]["denominator_value"] == 11
    assert metrics["blocker_recall"]["value"] == 1 / 11


def test_zero_denominator_score_counts_are_not_vacuous():
    rows = [
        {
            "source": "simulated",
            "blocker_recall": None,
            "blocker_recall_numerator": 0,
            "blocker_recall_denominator": 0,
        }
    ]
    metrics = {
        row["id"]: row for row in benchmark_metrics([], score_rows=rows)
    }
    assert metrics["blocker_recall_simulated"]["numerator_value"] == 0
    assert metrics["blocker_recall_simulated"]["denominator_value"] == 0
    assert metrics["blocker_recall_simulated"]["value"] is None


def test_measured_cost_per_finding_uses_measured_match_counts():
    usage = UsageCost(
        input_tokens=10,
        output_tokens=5,
        usd="0.001",
        source=DataSource.measured,
        component="jev",
        model="jev",
    )
    score_rows = [
        {
            "source": "measured",
            "blocker_recall": 1.0,
            "blocker_recall_numerator": 2,
            "blocker_recall_denominator": 2,
            "material_recall_including_blocker": 1.0,
            "material_recall_including_blocker_numerator": 3,
            "material_recall_including_blocker_denominator": 3,
        }
    ]
    metrics = {
        row["id"]: row
        for row in benchmark_metrics(
            [_record(usage=[usage], sol_invoked=False)], score_rows=score_rows
        )
    }
    assert metrics["cost_per_blocker"]["value"] == 0.0005
    assert metrics["cost_per_blocker"]["numerator_value"] == 0.001
    assert metrics["cost_per_blocker"]["denominator_value"] == 2
    assert metrics["cost_per_material_finding"]["value"] == 0.001 / 3
    assert metrics["cost_per_material_finding"]["denominator_value"] == 3


def test_measured_cost_zero_match_reasons_are_specific():
    usage = UsageCost(
        input_tokens=10,
        output_tokens=5,
        usd="0.001",
        source=DataSource.measured,
        component="jev",
        model="jev",
    )
    score_rows = [
        {
            "source": "measured",
            "blocker_recall": None,
            "blocker_recall_numerator": 0,
            "blocker_recall_denominator": 0,
            "material_recall_including_blocker": None,
            "material_recall_including_blocker_numerator": 0,
            "material_recall_including_blocker_denominator": 0,
        }
    ]
    metrics = {
        row["id"]: row
        for row in benchmark_metrics(
            [_record(usage=[usage], sol_invoked=False)], score_rows=score_rows
        )
    }
    assert (
        metrics["cost_per_material_finding"]["unavailable_reason"]
        == "no_matched_material_findings"
    )
    assert metrics["cost_per_blocker"]["unavailable_reason"] == "no_matched_blockers"


def test_resume_key_changes_with_model_and_effort(tmp_path: Path):
    case = ReviewCase(id="config_resume")
    Runner(output_dir=tmp_path, model="model-a", effort="low").run([case], ["A0"])
    assert len(Runner(output_dir=tmp_path, model="model-a", effort="low").run([case], ["A0"])) == 1
    records = Runner(output_dir=tmp_path, model="model-b", effort="high").run([case], ["A0"])
    assert len(records) == 2
    assert {record.config_digest for record in records}.__len__() == 2


def test_resume_effort_only_difference_and_collision_retry_deduplicate(tmp_path: Path):
    case = ReviewCase(id="effort_resume")
    low = Runner(output_dir=tmp_path, model="same-model", effort="low")
    low.run([case], ["A0"])
    medium = Runner(output_dir=tmp_path, model="same-model", effort="medium")
    records = medium.run([case], ["A0"])
    assert len(records) == 2
    assert len(medium.run([case], ["A0"])) == 2

    collision_dir = tmp_path / "collision"
    collision_dir.mkdir()
    collision = Runner(output_dir=collision_dir)
    canonical = str(
        uuid5(
            NAMESPACE_URL,
            _run_seed(
                case,
                "A0",
                collision.backend,
                collision.model,
                collision.effort,
                config_digest=collision._config_digest("A0"),
            ),
        )
    )
    (collision_dir / canonical).mkdir()
    first = collision.run([case], ["A0"])
    assert len(first) == 1
    retry_run_id = first[0].run_id
    assert retry_run_id != canonical
    assert len(collision.run([case], ["A0"])) == 1
