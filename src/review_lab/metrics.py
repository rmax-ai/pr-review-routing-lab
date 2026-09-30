"""Registry-shaped benchmark observations.

The values here are descriptive summaries of a run.  They do not choose a
threshold, estimate a population parameter, or turn mock observations into a
quality claim.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from math import ceil
from typing import Any

from .costing import UnpricedUsageError, usage_cost
from .models import DataSource, GoldCase, RunRecord
from .scoring import route_metrics


def percentile(values: Iterable[float], quantile: float) -> float | None:
    """Return a deterministic nearest-rank percentile."""

    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be between zero and one")
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    rank = max(1, ceil(len(ordered) * quantile))
    index = min(len(ordered) - 1, rank - 1)
    return ordered[index]


def _metric(
    metric_id: str,
    *,
    population: str,
    numerator: str | float,
    denominator: str | float,
    value: float | None,
    source: str,
    unavailable_reason: str | None = None,
) -> dict[str, Any]:
    numerator_value = numerator if isinstance(numerator, (int, float)) else None
    denominator_value = denominator if isinstance(denominator, (int, float)) else None
    return {
        "id": metric_id,
        "population": population,
        "numerator": numerator,
        "denominator": denominator,
        "value": value,
        "numerator_value": numerator_value,
        "denominator_value": denominator_value,
        "source": source,
        "missing_data_rule": "NA_at_zero",
        "computation": "deterministic",
        "unavailable_reason": unavailable_reason,
    }


def _stage_latencies(records: list[RunRecord]) -> list[float]:
    return [float(stage.duration_ms) for record in records for stage in record.stages]


def _overall_latencies(records: list[RunRecord]) -> list[float]:
    values: list[float] = []
    for record in records:
        usage = [float(item.latency_ms) for item in record.usage if item.latency_ms is not None]
        if usage:
            values.append(sum(usage))
        else:
            values.append(sum(float(stage.duration_ms) for stage in record.stages))
    return values


def _wall_seconds(records: list[RunRecord]) -> float | None:
    timestamps = [
        datetime.fromisoformat(timestamp)
        for record in records
        for stage in record.stages
        for timestamp in (stage.started_at, stage.ended_at)
    ]
    if not timestamps:
        return None
    seconds = (max(timestamps) - min(timestamps)).total_seconds()
    return seconds if seconds > 0 else None


def _expected_usage_components(record: RunRecord) -> set[str]:
    """Return components whose usage a completed record could have emitted."""

    expected: set[str] = set()
    if record.jev_calls:
        expected.add("jev")
    if record.sol_invoked:
        expected.add("sol_review")
        if any(stage.name == "dual_review" for stage in record.stages):
            expected.add("dual_review")
    if any(stage.name == "human_review" for stage in record.stages):
        expected.add("human")
    return expected


_SCORE_RATE_DEFINITIONS: dict[str, tuple[str, str, str]] = {
    "blocker_recall": ("expected_blockers", "matched_blockers", "expected_blockers"),
    "material_recall_including_blocker": (
        "expected_material_and_blocker",
        "matched_material_and_blocker",
        "expected_material_and_blocker",
    ),
    "material_recall_only": ("expected_material", "matched_material", "expected_material"),
    "requirement_coverage_recall": (
        "cited_expected_requirements",
        "independently_covered",
        "cited_expected_requirements",
    ),
    "spurious_blocker_rate": ("produced_findings", "unmatched_blockers", "produced_findings"),
    "severity_exactness_rate": (
        "matched_findings",
        "exact_severity_matches",
        "matched_findings",
    ),
    "overcall_rate": ("produced_findings", "unmatched_findings", "produced_findings"),
}


def _usage_metadata(
    records: list[RunRecord],
    source: DataSource,
    items: list[Any],
) -> dict[str, Any]:
    """Describe a source partition, including unavailable usage entries."""

    expected: set[str] = set()
    available: set[str] = set()
    unavailable: set[str] = set()
    for record in records:
        if (
            (source == DataSource.measured and record.backend != "live")
            or (source == DataSource.simulated and record.backend != "mock")
        ):
            continue
        expected.update(_expected_usage_components(record))
    for item in items:
        if item.usage_source == "unavailable":
            unavailable.add(item.component)
        else:
            available.add(item.component)
    missing = sorted((expected | unavailable) - available)
    missing_expected = sorted(expected - available - unavailable)
    unavailable_count = sum(item.usage_source == "unavailable" for item in items)
    partial_reasons = (
        [f"partial_usage_components:{unavailable_count}"]
        if available and unavailable_count
        else [f"missing_usage_component:{component}" for component in missing_expected]
        if available and missing_expected
        else []
    )
    return {
        "usage_components": sorted(available),
        "usage_components_expected": sorted(expected),
        "usage_components_missing": missing,
        "usage_component_complete": not missing and not unavailable,
        "unavailable_usage_items": unavailable_count,
        "partial_reasons": partial_reasons,
    }


def benchmark_metrics(
    records: Iterable[RunRecord],
    *,
    gold_by_case: Mapping[str, GoldCase] | None = None,
    score_rows: Iterable[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build all registry metric IDs with explicit missing values."""

    rows = list(records)
    gold = gold_by_case or {}
    output: dict[str, dict[str, Any]] = {}
    for row in route_metrics(rows, gold):
        output[row["id"]] = {
            **row,
            "value": row.get("value"),
        }

    score_values = list(score_rows or [])
    for metric_id, (population, numerator_name, denominator_name) in (
        _SCORE_RATE_DEFINITIONS.items()
    ):
        for source, suffix in (("measured", ""), ("simulated", "_simulated")):
            source_rows = [
                row
                for row in score_values
                if getattr(row.get("source"), "value", row.get("source")) == source
            ]
            numerator_key = f"{metric_id}_numerator"
            denominator_key = f"{metric_id}_denominator"
            pairs = [
                (int(row[numerator_key]), int(row[denominator_key]))
                for row in source_rows
                if row.get(numerator_key) is not None and row.get(denominator_key) is not None
            ]
            numerator_count = sum(pair[0] for pair in pairs) if pairs else None
            denominator_count = sum(pair[1] for pair in pairs) if pairs else None
            value = (
                numerator_count / denominator_count
                if numerator_count is not None and denominator_count
                else None
            )
            output[f"{metric_id}{suffix}"] = _metric(
                f"{metric_id}{suffix}",
                population=population,
                numerator=numerator_name,
                denominator=denominator_name,
                value=value,
                source="score",
            )
            output[f"{metric_id}{suffix}"]["numerator_value"] = numerator_count
            output[f"{metric_id}{suffix}"]["denominator_value"] = denominator_count

    for source, suffix in (("measured", ""), ("simulated", "_simulated")):
        source_rows = [
            row
            for row in score_values
            if getattr(row.get("source"), "value", row.get("source")) == source
        ]
        values = [
            int(row["required_but_unmentioned"])
            for row in source_rows
            if row.get("required_but_unmentioned") is not None
        ]
        output[f"required_but_unmentioned{suffix}"] = _metric(
            f"required_but_unmentioned{suffix}",
            population="required_requirements",
            numerator="uncited_requirements",
            denominator="required_requirements",
            value=sum(values) if values else None,
            source="score",
        )
        output[f"required_but_unmentioned{suffix}"]["missing_data_rule"] = "zero_at_zero"
        output[f"required_but_unmentioned{suffix}"]["numerator_value"] = (
            sum(values) if values else None
        )
        # This count metric is a population sum, not a rate.  Retain the
        # number of scored observations for the existing report shape.
        output[f"required_but_unmentioned{suffix}"]["denominator_value"] = (
            len(values) if values else None
        )

    measured_usage = [
        item
        for record in rows
        for item in record.usage
        if item.source == DataSource.measured
    ]
    simulated_usage = [
        item
        for record in rows
        for item in record.usage
        if item.source == DataSource.simulated
    ]
    measured_cases = sum(
        any(
            item.source == DataSource.measured and item.usage_source != "unavailable"
            for item in record.usage
        )
        for record in rows
    )
    simulated_cases = sum(
        any(
            item.source == DataSource.simulated and item.usage_source != "unavailable"
            for item in record.usage
        )
        for record in rows
    )
    measured_usage_meta = _usage_metadata(rows, DataSource.measured, measured_usage)
    simulated_usage_meta = _usage_metadata(rows, DataSource.simulated, simulated_usage)

    def available_items(items: list[Any]) -> list[Any]:
        return [item for item in items if item.usage_source != "unavailable"]

    def partition_reason(items: list[Any]) -> str:
        available = available_items(items)
        if not items or not available:
            return "no_available_usage"
        unavailable_count = sum(item.usage_source == "unavailable" for item in items)
        if unavailable_count:
            return f"partial_usage_components:{unavailable_count}"
        return ""

    def add_usage_reasons(
        metric_id: str, metadata: Mapping[str, Any], reason: str | None
    ) -> None:
        reasons = list(metadata.get("partial_reasons", []))
        if reason and reason != "no_available_usage":
            reasons.append(reason)
        output[metric_id]["partial_reasons"] = sorted(set(reasons))

    def token_value(items: list[Any]) -> tuple[float | None, str | None]:
        if not items:
            return None, "no_available_usage"
        if any(item.input_tokens is None or item.output_tokens is None for item in items):
            return None, "incomplete_token_usage"
        return float(sum(item.input_tokens + item.output_tokens for item in items)), None

    measured_available = available_items(measured_usage)
    measured_partition_reason = partition_reason(measured_usage)
    if measured_partition_reason:
        tokens, token_reason = None, measured_partition_reason
    else:
        tokens, token_reason = token_value(measured_available)
    output["tokens"] = _metric(
        "tokens",
        population="measured_cases",
        numerator="input_plus_output_tokens",
        denominator="measured_cases",
        value=tokens / measured_cases if tokens is not None and measured_cases else None,
        source="usage",
        unavailable_reason=token_reason,
    )
    output["tokens"].update(measured_usage_meta)
    add_usage_reasons("tokens", measured_usage_meta, token_reason)
    simulated_available = available_items(simulated_usage)
    simulated_partition_reason = partition_reason(simulated_usage)
    if simulated_partition_reason:
        simulated_tokens, simulated_token_reason = None, simulated_partition_reason
    else:
        simulated_tokens, simulated_token_reason = token_value(simulated_available)
    output["tokens_simulated"] = _metric(
        "tokens_simulated",
        population="simulated_cases",
        numerator="input_plus_output_tokens",
        denominator="simulated_cases",
        value=(
            simulated_tokens / simulated_cases
            if simulated_tokens is not None and simulated_cases
            else None
        ),
        source="usage",
        unavailable_reason=simulated_token_reason,
    )
    output["tokens_simulated"].update(simulated_usage_meta)
    add_usage_reasons("tokens_simulated", simulated_usage_meta, simulated_token_reason)

    def cost_value(items: list[Any]) -> tuple[float | None, str | None]:
        if not items:
            return None, "no_available_usage"
        try:
            return float(usage_cost(items)), None
        except UnpricedUsageError:
            return None, "unpriceable_usage"

    if measured_partition_reason:
        total_cost, cost_reason = None, measured_partition_reason
    else:
        total_cost, cost_reason = cost_value(measured_available)
    output["cost_per_pr"] = _metric(
        "cost_per_pr",
        population="measured_cases",
        numerator="total_cost",
        denominator="measured_cases",
        value=total_cost / measured_cases if total_cost is not None and measured_cases else None,
        source="costing",
        unavailable_reason=cost_reason,
    )
    output["cost_per_pr"].update(measured_usage_meta)
    add_usage_reasons("cost_per_pr", measured_usage_meta, cost_reason)
    if simulated_partition_reason:
        simulated_cost, simulated_cost_reason = None, simulated_partition_reason
    else:
        simulated_cost, simulated_cost_reason = cost_value(simulated_available)
    output["cost_per_pr_simulated"] = _metric(
        "cost_per_pr_simulated",
        population="simulated_cases",
        numerator="total_cost",
        denominator="simulated_cases",
        value=(
            simulated_cost / simulated_cases
            if simulated_cost is not None and simulated_cases
            else None
        ),
        source="costing",
        unavailable_reason=simulated_cost_reason,
    )
    output["cost_per_pr_simulated"].update(simulated_usage_meta)
    add_usage_reasons("cost_per_pr_simulated", simulated_usage_meta, simulated_cost_reason)
    score_source_rows = {
        source: [
            row
            for row in score_values
            if getattr(row.get("source"), "value", row.get("source")) == source
        ]
        for source in ("measured", "simulated")
    }
    def scored_count(source: str, key: str) -> int:
        rows_for_source = score_source_rows[source]
        count_key = f"{key}_numerator"
        return sum(
            int(row[count_key])
            for row in rows_for_source
            if row.get(count_key) is not None
        )

    for metric_id, denominator in (
        ("cost_per_material_finding", "matched_material_findings"),
        ("cost_per_blocker", "matched_blockers"),
    ):
        matched_count = scored_count(
            "measured",
            (
                "material_recall_including_blocker"
                if metric_id == "cost_per_material_finding"
                else "blocker_recall"
            ),
        )
        reason = cost_reason
        if reason is None and not matched_count:
            reason = (
                "no_matched_material_findings"
                if metric_id == "cost_per_material_finding"
                else "no_matched_blockers"
            )
        output[metric_id] = _metric(
            metric_id,
            population=denominator,
            numerator="total_cost",
            denominator=denominator,
            value=(
                total_cost / matched_count
                if total_cost is not None and matched_count
                else None
            ),
            source="costing",
            unavailable_reason=reason,
        )
        output[metric_id]["numerator_value"] = total_cost
        output[metric_id]["denominator_value"] = matched_count
        output[metric_id].update(measured_usage_meta)
        add_usage_reasons(metric_id, measured_usage_meta, cost_reason)

    overall = _overall_latencies(rows)
    stages = _stage_latencies(rows)
    output["latency_p50_overall"] = _metric(
        "latency_p50_overall",
        population="cases",
        numerator="p50_latency_ms",
        denominator="cases",
        value=percentile(overall, 0.50),
        source="observation",
    )
    output["latency_p95_overall"] = _metric(
        "latency_p95_overall",
        population="cases",
        numerator="p95_latency_ms",
        denominator="cases",
        value=percentile(overall, 0.95),
        source="observation",
    )
    output["latency_p50_per_stage"] = _metric(
        "latency_p50_per_stage",
        population="stage_observations",
        numerator="p50_stage_latency_ms",
        denominator="stage_observations",
        value=percentile(stages, 0.50),
        source="observation",
    )
    output["latency_p95_per_stage"] = _metric(
        "latency_p95_per_stage",
        population="stage_observations",
        numerator="p95_stage_latency_ms",
        denominator="stage_observations",
        value=percentile(stages, 0.95),
        source="observation",
    )
    wall_seconds = _wall_seconds(rows)
    output["throughput"] = _metric(
        "throughput",
        population="completed_cases",
        numerator="cases",
        denominator="elapsed_wall_time",
        value=len(rows) / wall_seconds if wall_seconds else None,
        source="observation",
    )

    # Preserve registry order when the caller later merges this list with the
    # declarative metric file.
    return [output[key] for key in sorted(output)]
