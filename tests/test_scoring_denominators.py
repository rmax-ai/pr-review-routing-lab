import json
import time

from review_lab.models import (
    DefectClass,
    Finding,
    GoldCase,
    Route,
    RunRecord,
    Severity,
    StageRecord,
    Terminal,
)
from review_lab.scoring import required_but_unmentioned, route_metrics, score_findings


def _row(
    run_id: str,
    *,
    route: Route = Route.remediate_simulated,
    loops: int = 0,
    error: str | None = None,
    simulated: bool = False,
    linked: bool = True,
) -> RunRecord:
    stages = (
        [
            StageRecord(
                name="remediation_loop",
                started_at="2025-01-01T00:00:00+00:00",
                ended_at="2025-01-01T00:00:00+00:00",
                duration_ms=0,
                data={"simulated": simulated},
            )
        ]
        if loops
        else []
    )
    return RunRecord(
        run_id=run_id,
        case_ref="a" * 12,
        case_id=run_id,
        linked_case_id="fixed-head" if linked else None,
        case_digest="a" * 64,
        architecture="A4",
        stages=stages,
        route=route,
        terminal=(
            Terminal.error_terminal
            if error
            else Terminal.routed_human
            if route == Route.human_review
            else Terminal.routed_remediate_simulated
        ),
        escalated=False,
        sol_invoked=False,
        jev_calls=0,
        remediation_loops=loops,
        config_digest="b" * 64,
        backend="mock",
        error=error,
    )


def test_review_loop_denominator_is_remediation_eligible_and_split():
    # Replay artifacts require the fixed-head link; unrelated remediation
    # routes must not enlarge the loop denominator.
    rows = [
        _row("loop_a", loops=0),
        _row("loop_b", loops=1, simulated=True),
        _row("loop_c", loops=2, simulated=False),
        _row("not_linked", loops=2, simulated=True, linked=False),
    ]

    metrics = {row["id"]: row for row in route_metrics(rows, {})}

    assert metrics["review_loops"]["denominator"] == 3
    assert metrics["review_loops"]["numerator"] == 2
    assert metrics["review_loops_simulated"]["numerator"] == 1


def test_error_rows_are_excluded_from_route_denominators():
    rows = [_row("good"), _row("bad", error="runner_error")]

    metrics = {row["id"]: row for row in route_metrics(rows, {})}

    assert metrics["error_rows_skipped"]["value"] == 1
    assert metrics["remediation_eligibility_rate"]["denominator"] == 1
    assert metrics["human_avoidance_rate"]["denominator"] == 1
    assert metrics["jev_calls_per_pr"]["denominator"] == 1


def test_human_routes_remain_in_route_denominators():
    rows = [_row("automated"), _row("human", route=Route.human_review)]

    metrics = {row["id"]: row for row in route_metrics(rows, {})}

    assert metrics["remediation_eligibility_rate"]["denominator"] == 2
    assert metrics["human_avoidance_rate"]["denominator"] == 2
    assert metrics["human_avoidance_rate"]["numerator"] == 1
    assert metrics["jev_calls_per_pr"]["denominator"] == 2


def test_required_but_unmentioned_uses_mandatory_requirements():
    gold = GoldCase.model_validate_json(
        json.dumps(
            {
                "case_id": "requirements",
                "expected_findings": [],
                "human_required": False,
                "verdict_expectation": "accept",
                "labeled_by": "operator",
            }
        )
    )

    assert (
        required_but_unmentioned(
            gold,
            [],
            [{"id": "R1", "mandatory": True}, {"id": "R2", "mandatory": False}],
        )
        == 1
    )


def test_matching_scales_without_exponential_bitmask_state():
    expected = [
        {
            "severity": "material",
            "defect_class": "other",
            "requirement_refs": [],
            "match": {"location_contains": f"file_{index}"},
        }
        for index in range(60)
    ]
    gold = GoldCase.model_validate_json(
        json.dumps(
            {
                "case_id": "performance",
                "expected_findings": expected,
                "human_required": False,
                "verdict_expectation": "changes_required",
                "labeled_by": "operator",
            }
        )
    )
    findings = [
        Finding(
            id=f"F{index}",
            severity=Severity.material,
            defect_class=DefectClass.other,
            evidence="evidence",
            confidence=0.8,
            location=f"file_{index}",
        )
        for index in range(60)
    ]

    started = time.monotonic()
    score = score_findings(findings, gold)

    assert score.exact_matches == 60
    assert time.monotonic() - started < 2.0
