import json

import yaml

from review_lab.cli import _score_record_rows
from review_lab.metrics import benchmark_metrics
from review_lab.models import (
    DataSource,
    DefectClass,
    Finding,
    GoldCase,
    HarnessId,
    ReviewVerdict,
    Route,
    RunRecord,
    Severity,
    Terminal,
    UsageCost,
)


def test_usage_metrics_partition_measured_and_simulated():
    def row(run_id: str, source: DataSource) -> RunRecord:
        return RunRecord(
            run_id=run_id,
            case_ref="a" * 12,
            case_id=run_id,
            case_digest="a" * 64,
            architecture="A0",
            route=Route.human_review,
            terminal=Terminal.routed_human,
            escalated=True,
            sol_invoked=False,
            jev_calls=0,
            remediation_loops=0,
            config_digest="b" * 64,
            backend="live" if source == DataSource.measured else "mock",
            usage=[
                UsageCost(
                    input_tokens=10,
                    output_tokens=5,
                    usd="0.001",
                    source=source,
                    component="jev",
                    model="jev",
                )
            ],
        )

    metrics = {
        item["id"]: item
        for item in benchmark_metrics(
            [row("measured", DataSource.measured), row("simulated", DataSource.simulated)]
        )
    }

    assert metrics["tokens"]["value"] == 15
    assert metrics["tokens_simulated"]["value"] == 15
    assert metrics["cost_per_pr"]["value"] == 0.001
    assert metrics["cost_per_pr_simulated"]["value"] == 0.001


def test_unavailable_usage_is_not_reported_as_zero():
    record = RunRecord(
        run_id="unavailable",
        case_ref="a" * 12,
        case_id="unavailable",
        case_digest="a" * 64,
        architecture="A0",
        route=Route.human_review,
        terminal=Terminal.routed_human,
        escalated=True,
        sol_invoked=False,
        jev_calls=0,
        remediation_loops=0,
        config_digest="b" * 64,
        backend="mock",
        usage=[
            UsageCost(
                source=DataSource.simulated,
                component="human",
                usage_source="unavailable",
            )
        ],
    )

    metrics = {item["id"]: item for item in benchmark_metrics([record])}

    assert metrics["tokens_simulated"]["value"] is None
    assert metrics["cost_per_pr_simulated"]["value"] is None
    assert metrics["tokens_simulated"]["unavailable_reason"] == "no_available_usage"
    assert metrics["cost_per_pr_simulated"]["unavailable_reason"] == "no_available_usage"


def test_score_metrics_are_partitioned_by_source_and_missing_source_is_none():
    base = {
        "material_recall_including_blocker": 0.5,
        "material_recall_including_blocker_numerator": 1,
        "material_recall_including_blocker_denominator": 2,
        "material_recall_only": 0.0,
        "material_recall_only_numerator": 0,
        "material_recall_only_denominator": 1,
        "requirement_coverage_recall": 1.0,
        "requirement_coverage_recall_numerator": 1,
        "requirement_coverage_recall_denominator": 1,
        "required_but_unmentioned": 2,
        "spurious_blocker_rate": 0.0,
        "spurious_blocker_rate_numerator": 0,
        "spurious_blocker_rate_denominator": 1,
        "severity_exactness_rate": 1.0,
        "severity_exactness_rate_numerator": 1,
        "severity_exactness_rate_denominator": 1,
        "overcall_rate": 0.0,
        "overcall_rate_numerator": 0,
        "overcall_rate_denominator": 1,
    }
    rows = [
        {
            "source": "measured",
            "blocker_recall": 0.0,
            "blocker_recall_numerator": 0,
            "blocker_recall_denominator": 1,
            **base,
        },
        {
            "source": "simulated",
            "blocker_recall": 1.0,
            "blocker_recall_numerator": 1,
            "blocker_recall_denominator": 1,
            **base,
        }
    ]

    metrics = {item["id"]: item for item in benchmark_metrics([], score_rows=rows)}

    assert metrics["blocker_recall"]["value"] == 0.0
    assert metrics["blocker_recall_simulated"]["value"] == 1.0
    assert metrics["blocker_recall"]["population"] == "expected_blockers"
    assert metrics["blocker_recall"]["numerator"] == "matched_blockers"
    assert metrics["blocker_recall"]["denominator"] == "expected_blockers"
    assert metrics["blocker_recall"]["numerator_value"] == 0
    assert metrics["blocker_recall"]["denominator_value"] == 1
    assert metrics["required_but_unmentioned"]["value"] == 2
    assert metrics["required_but_unmentioned_simulated"]["value"] == 2

    measured_only = {
        item["id"]: item
        for item in benchmark_metrics([], score_rows=[rows[0]])
    }
    assert measured_only["blocker_recall_simulated"]["value"] is None
    assert measured_only["required_but_unmentioned_simulated"]["value"] is None


def test_token_and_cost_availability_boundaries():
    def record(*usage: UsageCost) -> RunRecord:
        return RunRecord(
            run_id="availability",
            case_ref="a" * 12,
            case_id="availability",
            case_digest="a" * 64,
            architecture="A0",
            route=Route.human_review,
            terminal=Terminal.routed_human,
            escalated=True,
            sol_invoked=False,
            jev_calls=0,
            remediation_loops=0,
            config_digest="b" * 64,
            backend="live",
            usage=list(usage),
        )

    partial = record(
        UsageCost(
            input_tokens=10,
            source=DataSource.measured,
            component="jev",
            usd="0.001",
        )
    )
    partial_metrics = {
        item["id"]: item for item in benchmark_metrics([partial])
    }
    assert partial_metrics["tokens"]["value"] is None
    assert partial_metrics["tokens"]["unavailable_reason"] == "incomplete_token_usage"
    assert partial_metrics["cost_per_pr"]["value"] == 0.001

    partial_components = record(
        UsageCost(
            input_tokens=10,
            output_tokens=5,
            source=DataSource.measured,
            component="jev",
            usd="0.001",
        ),
        UsageCost(
            source=DataSource.measured,
            component="sol_review",
            usage_source="unavailable",
        ),
    )
    partial_component_metrics = {
        item["id"]: item for item in benchmark_metrics([partial_components])
    }
    for metric_id in ("tokens", "cost_per_pr"):
        assert partial_component_metrics[metric_id]["value"] is None
        assert (
            partial_component_metrics[metric_id]["unavailable_reason"]
            == "partial_usage_components:1"
        )

    fully_available = record(
        UsageCost(
            input_tokens=10,
            output_tokens=5,
            source=DataSource.measured,
            component="jev",
            usd="0.001",
        ),
        UsageCost(
            input_tokens=20,
            output_tokens=10,
            source=DataSource.measured,
            component="sol_review",
            usd="0.002",
        ),
    )
    fully_available_metrics = {
        item["id"]: item for item in benchmark_metrics([fully_available])
    }
    assert fully_available_metrics["tokens"]["value"] == 45
    assert fully_available_metrics["cost_per_pr"]["value"] == 0.003

    unpriced = record(
        UsageCost(
            input_tokens=10,
            output_tokens=5,
            source=DataSource.measured,
            component="jev",
            model="unknown",
        )
    )
    unpriced_metrics = {
        item["id"]: item for item in benchmark_metrics([unpriced])
    }
    assert unpriced_metrics["tokens"]["value"] == 15
    assert unpriced_metrics["cost_per_pr"]["value"] is None
    assert unpriced_metrics["cost_per_pr"]["unavailable_reason"] == "unpriceable_usage"
    for metric_id in ("cost_per_material_finding", "cost_per_blocker"):
        assert unpriced_metrics[metric_id]["value"] is None
        assert unpriced_metrics[metric_id]["unavailable_reason"] == "unpriceable_usage"

    priced = record(
        UsageCost(
            input_tokens=10,
            output_tokens=5,
            source=DataSource.measured,
            component="jev",
            usd="0.001",
        )
    )
    priced_metrics = {item["id"]: item for item in benchmark_metrics([priced])}
    assert priced_metrics["tokens"]["value"] == 15
    assert priced_metrics["cost_per_pr"]["value"] == 0.001
    assert priced_metrics["cost_per_pr"]["unavailable_reason"] is None


def test_latency_only_usage_is_not_token_complete_or_unpriced_cost():
    record = RunRecord(
        run_id="latency-only",
        case_ref="a" * 12,
        case_id="latency-only",
        case_digest="a" * 64,
        architecture="A0",
        route=Route.human_review,
        terminal=Terminal.routed_human,
        escalated=True,
        sol_invoked=False,
        jev_calls=0,
        remediation_loops=0,
        config_digest="b" * 64,
        backend="live",
        usage=[
            UsageCost(
                latency_ms=7,
                usd="0",
                source=DataSource.measured,
                component="jev",
            )
        ],
    )

    metrics = {item["id"]: item for item in benchmark_metrics([record])}

    assert metrics["tokens"]["value"] is None
    assert metrics["tokens"]["unavailable_reason"] == "incomplete_token_usage"
    assert metrics["cost_per_pr"]["value"] == 0.0
    assert metrics["cost_per_pr"]["unavailable_reason"] is None


def test_scored_recalls_skip_error_human_and_empty_verdicts(tmp_path):
    gold = GoldCase.model_validate_json(
        json.dumps(
            {
            "case_id": "score_case",
            "expected_findings": [
                {
                    "severity": "material",
                    "defect_class": "other",
                    "match": {"location_contains": "vulnerable.py"},
                }
            ],
            "human_required": False,
            "verdict_expectation": "changes_required",
            "labeled_by": "operator",
            }
        )
    )
    gold_root = tmp_path / "gold" / "score_case"
    gold_root.mkdir(parents=True)
    (gold_root / "expected.yaml").write_text(
        yaml.safe_dump(json.loads(gold.model_dump_json())), encoding="utf-8"
    )
    verdict_root = tmp_path / "verdicts"
    verdict_root.mkdir()

    def record(run_id: str, architecture: str, *, error: str | None = None) -> RunRecord:
        return RunRecord(
            run_id=run_id,
            case_ref="a" * 12,
            case_id="score_case",
            case_digest="a" * 64,
            architecture=architecture,
            route=Route.human_review,
            terminal=Terminal.error_terminal if error else Terminal.routed_human,
            escalated=True,
            sol_invoked=True,
            jev_calls=1,
            remediation_loops=0,
            config_digest="b" * 64,
            backend="mock",
            error=error,
        )

    def verdict(architecture: str, **updates: object) -> None:
        values = {
            "case_id": "score_case",
            "case_digest": "a" * 64,
            "head_digest": "b" * 64,
            "packet_digest": "c" * 64,
            "verdict": "changes_required",
            "model": "mock",
            "effort": "low",
            "harness": HarnessId.mock_codex,
            **updates,
        }
        value = ReviewVerdict(**values)
        (verdict_root / f"score_case-{architecture}.json").write_text(
            value.model_dump_json(), encoding="utf-8"
        )

    error = record("error", "A1", error="runner_error")
    human = record("human", "A2")
    empty = record("empty", "A3")
    good = record("good", "A4")
    verdict("A2", verdict="human_decision")
    verdict("A3")
    verdict(
        "A4",
        findings=[
            Finding(
                id="F1",
                severity=Severity.material,
                defect_class=DefectClass.other,
                evidence="evidence",
                confidence=0.9,
                location="vulnerable.py",
            )
        ],
    )

    rows, _ = _score_record_rows(
        [error, human, empty, good], tmp_path / "gold", tmp_path
    )

    assert [row["architecture"] for row in rows] == ["A4"]
    assert rows[0]["material_recall_only"] == 1.0
