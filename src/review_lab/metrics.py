"""Registry-shaped benchmark observations.

The values here are descriptive summaries of a run.  They do not choose a
threshold, estimate a population parameter, or turn mock observations into a
quality claim.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from math import ceil
from statistics import mean
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
    numerator: str,
    denominator: str,
    value: float | None,
    source: str,
    unavailable_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "id": metric_id,
        "population": population,
        "numerator": numerator,
        "denominator": denominator,
        "value": value,
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
    score_metric_ids = (
        "blocker_recall",
        "material_recall_including_blocker",
        "material_recall_only",
        "requirement_coverage_recall",
        "spurious_blocker_rate",
        "severity_exactness_rate",
        "overcall_rate",
    )
    score_metric_ids += ("required_but_unmentioned",)
    for metric_id in score_metric_ids:
        for source, suffix in (("measured", ""), ("simulated", "_simulated")):
            source_rows = [
                row
                for row in score_values
                if getattr(row.get("source"), "value", row.get("source")) == source
            ]
            if metric_id == "required_but_unmentioned":
                values = [
                    int(row[metric_id])
                    for row in source_rows
                    if row.get(metric_id) is not None
                ]
                value = sum(values) if values else None
                numerator = "uncited_requirements"
            else:
                values = [
                    float(row[metric_id])
                    for row in source_rows
                    if row.get(metric_id) is not None
                ]
                value = mean(values) if values else None
                numerator = f"mean_{metric_id}"
            output[f"{metric_id}{suffix}"] = _metric(
                f"{metric_id}{suffix}",
                population=f"scored_review_rows_{source}",
                numerator=numerator,
                denominator=f"scored_review_rows_{source}",
                value=value,
                source="score",
            )

    measured_usage = [
        item
        for record in rows
        for item in record.usage
        if item.source == DataSource.measured and item.usage_source != "unavailable"
    ]
    simulated_usage = [
        item
        for record in rows
        for item in record.usage
        if item.source == DataSource.simulated and item.usage_source != "unavailable"
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
    def token_value(items: list[Any]) -> tuple[float | None, str | None]:
        if not items:
            return None, "no_available_usage"
        if any(item.input_tokens is None or item.output_tokens is None for item in items):
            return None, "incomplete_token_usage"
        return float(sum(item.input_tokens + item.output_tokens for item in items)), None

    tokens, token_reason = token_value(measured_usage)
    output["tokens"] = _metric(
        "tokens",
        population="measured_cases",
        numerator="input_plus_output_tokens",
        denominator="measured_cases",
        value=tokens / measured_cases if tokens is not None and measured_cases else None,
        source="usage",
        unavailable_reason=token_reason,
    )
    simulated_tokens, simulated_token_reason = token_value(simulated_usage)
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
    def cost_value(items: list[Any]) -> tuple[float | None, str | None]:
        if not items:
            return None, "no_available_usage"
        try:
            return float(usage_cost(items)), None
        except UnpricedUsageError:
            return None, "unpriceable_usage"

    total_cost, cost_reason = cost_value(measured_usage)
    output["cost_per_pr"] = _metric(
        "cost_per_pr",
        population="measured_cases",
        numerator="total_cost",
        denominator="measured_cases",
        value=total_cost / measured_cases if total_cost is not None and measured_cases else None,
        source="costing",
        unavailable_reason=cost_reason,
    )
    simulated_cost, simulated_cost_reason = cost_value(simulated_usage)
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
    for metric_id, denominator in (
        ("cost_per_material_finding", "matched_material_findings"),
        ("cost_per_blocker", "matched_blockers"),
    ):
        output[metric_id] = _metric(
            metric_id,
            population=denominator,
            numerator="total_cost",
            denominator=denominator,
            value=None,
            source="costing",
            unavailable_reason=cost_reason,
        )

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
