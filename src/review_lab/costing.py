"""Separated measured, simulated, and modeled cost arithmetic."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .models import DataSource, PricingConfig, Scenario, UsageCost
from .util import read_yaml

MONEY_QUANTUM = Decimal("0.000001")


class UnpricedUsageError(ValueError):
    """Usage was marked available but no authoritative price was supplied."""


def decimal(value: Decimal | str | float) -> Decimal:
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("invalid decimal") from exc
    if not result.is_finite() or result < 0:
        raise ValueError("money must be finite and non-negative")
    return result


def money(value: Decimal | str | float) -> str:
    return str(decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP))


def usage_cost(
    rows: Iterable[UsageCost],
    pricing: Mapping[str, tuple[str, str]] | None = None,
) -> str:
    total = Decimal(0)
    prices = pricing or {}
    for row in rows:
        if row.usage_source == "unavailable":
            continue
        if row.usd is not None:
            total += decimal(row.usd)
        elif row.model and row.model in prices:
            input_price, output_price = prices[row.model]
            total += Decimal(row.input_tokens or 0) * decimal(input_price)
            total += Decimal(row.output_tokens or 0) * decimal(output_price)
        else:
            raise UnpricedUsageError(
                f"usage for model {row.model or '<unknown>'} has no price or USD amount"
            )
    return money(total)


def load_pricing(path: str | Path) -> PricingConfig:
    raw = read_yaml(path)
    if isinstance(raw, dict) and "entries" not in raw and "pricing" in raw:
        raw = {"entries": raw["pricing"]}
    return PricingConfig.model_validate_json(json.dumps(raw))


def pricing_map(config: PricingConfig) -> dict[str, tuple[str, str]]:
    rows = sorted(config.entries, key=lambda item: (item.provider, item.model))
    models = [entry.model for entry in rows]
    if len(models) != len(set(models)):
        raise ValueError("pricing contains duplicate model names; UsageCost has no provider field")
    return {entry.model: (entry.input_usd_per_token, entry.output_usd_per_token) for entry in rows}


def _source_rows(rows: Iterable[UsageCost], source: DataSource) -> list[UsageCost]:
    return [row for row in rows if row.source == source]


def separated_tables(
    usage: Iterable[UsageCost],
    *,
    per_pr: int = 1,
    scenarios: Iterable[Mapping[str, Any]] | None = None,
    modeled_per_pr_cost: str = "0",
) -> dict[str, list[dict[str, str | int]]]:
    """Return mutually exclusive observed-live and simulated-fixture tables."""

    if per_pr <= 0:
        raise ValueError("per_pr must be positive")
    rows = list(usage)
    output: dict[str, list[dict[str, str | int]]] = {}
    for source, name in (
        (DataSource.measured, "observed-live"),
        (DataSource.simulated, "simulated-fixture"),
    ):
        selected = _source_rows(rows, source)
        total = usage_cost(selected)
        output[name] = [
            {
                "source": source.value,
                "n": per_pr,
                "total_usd": total,
                "usd_per_pr": money(Decimal(total) / per_pr) if per_pr else "NA",
            }
        ]
    output["modeled-scenario"] = (
        modeled_cost(scenarios or [], cost_per_pr=modeled_per_pr_cost)
        if scenarios is not None
        else []
    )
    return output


def cost_tables(
    observed_live: Iterable[UsageCost],
    simulated_fixture: Iterable[UsageCost],
    modeled_scenario: Iterable[Mapping[str, Any]],
) -> dict[str, list[dict[str, str | int]]]:
    """Build the three mutually exclusive source tables."""

    observed = list(observed_live)
    simulated = list(simulated_fixture)
    if any(row.source != DataSource.measured for row in observed):
        raise ValueError("observed-live table received a non-measured usage row")
    if any(row.source != DataSource.simulated for row in simulated):
        raise ValueError("simulated-fixture table received a non-simulated usage row")
    return {
        "observed-live": [
            {
                "source": "measured",
                "n": len(observed),
                "total_usd": usage_cost(observed),
            }
        ],
        "simulated-fixture": [
            {
                "source": "simulated",
                "n": len(simulated),
                "total_usd": usage_cost(simulated),
            }
        ],
        "modeled-scenario": modeled_cost(modeled_scenario),
    }


def modeled_cost(
    scenarios: Iterable[Mapping[str, Any]],
    *,
    cost_per_pr: str = "0",
    material_findings: int = 0,
    blocker_findings: int = 0,
) -> list[dict[str, str | int]]:
    """Compute the modeled scenario table with explicit zero denominators."""

    unit = decimal(cost_per_pr)
    rows = []
    for item in scenarios:
        try:
            raw = dict(item)
            if "monthly_volume" not in raw and "volume" in raw:
                raw["monthly_volume"] = raw.pop("volume")
            scenario = Scenario.model_validate(raw)
        except (TypeError, ValueError, ValidationError) as exc:
            raise ValueError("scenario values are invalid") from exc
        volume = scenario.monthly_volume
        high_risk_share = decimal(scenario.high_risk_share)
        human_minutes = decimal(scenario.human_minutes)
        hourly_rate = decimal(scenario.human_hourly_rate)
        concurrency = scenario.reviewer_concurrency
        human_cost_per_review = human_minutes / Decimal(60) * hourly_rate
        modeled_unit = unit + high_risk_share * human_cost_per_review
        total = modeled_unit * volume
        rows.append(
            {
                "source": "modeled",
                "monthly_volume": volume,
                "monthly_cost_usd": money(total),
                "usd_per_pr": money(modeled_unit),
                "high_risk_share": money(high_risk_share),
                "human_minutes": money(human_minutes),
                "human_hourly_rate": money(hourly_rate),
                "reviewer_concurrency": concurrency,
                "cost_per_material_finding_usd": (
                    money(total / material_findings) if material_findings else "NA"
                ),
                "cost_per_blocker_usd": (
                    money(total / blocker_findings) if blocker_findings else "NA"
                ),
            }
        )
    return sorted(rows, key=lambda row: int(row["monthly_volume"]))


def model_scenarios(
    path: str | Path,
    *,
    per_pr_cost: str = "0",
    per_pr_cost_alias: str | None = None,
) -> list[dict[str, str | int]]:
    raw = read_yaml(path)
    values = raw.get("scenarios", raw) if isinstance(raw, dict) else raw
    if not isinstance(values, list):
        raise ValueError("scenario file must contain a list")  # noqa: TRY004
    validated = [
        Scenario.model_validate_json(json.dumps(value)).model_dump(mode="json") for value in values
    ]
    return modeled_cost(
        validated,
        cost_per_pr=per_pr_cost_alias if per_pr_cost_alias is not None else per_pr_cost,
    )


def sensitivity(
    base_cost_per_pr: str,
    ranges: Mapping[str, Iterable[str | int | float]],
) -> list[dict[str, str]]:
    """Expand modeled assumptions into deterministic sensitivity rows."""

    names = sorted(ranges)
    rows: list[dict[str, str]] = []

    def visit(index: int, selected: dict[str, str]) -> None:
        if index == len(names):
            row = dict(selected)
            row["cost_per_pr"] = money(base_cost_per_pr)
            rows.append(row)
            return
        name = names[index]
        values = sorted(
            {str(value) for value in ranges[name]},
            key=lambda value: (
                0,
                Decimal(value),
            )
            if _is_decimal(value)
            else (1, value),
        )
        for value in values:
            selected[name] = str(value)
            visit(index + 1, selected)
        selected.pop(name, None)

    visit(0, {})
    return rows


def _is_decimal(value: str) -> bool:
    try:
        Decimal(value)
    except InvalidOperation:
        return False
    return True


def frontier_tables(
    metrics: Mapping[str, float | None],
    *,
    source: str = "modeled",
    n: int = 0,
) -> dict[str, list[dict[str, str | float | int | None]]]:
    """Produce table-shaped frontiers without implying an optimization result."""

    cost = metrics.get("cost_per_pr")
    return {
        "material_recall_vs_cost": [
            {
                "source": source,
                "n": n,
                "material_recall": metrics.get("material_recall"),
                "usd_per_pr": cost,
            }
        ],
        "blocker_recall_vs_human_escalation": [
            {
                "source": source,
                "n": n,
                "blocker_recall": metrics.get("blocker_recall"),
                "human_escalation_rate": metrics.get("human_escalation_rate"),
            }
        ],
        "latency_vs_automation": [
            {
                "source": source,
                "n": n,
                "latency_ms": metrics.get("latency_ms"),
                "automation_rate": metrics.get("automation_rate"),
            }
        ],
        "sol_avoidance_vs_gate_a_false_safe": [
            {
                "source": source,
                "n": n,
                "sol_avoidance_rate": metrics.get("sol_avoidance_rate"),
                "gate_a_false_safe_rate": metrics.get("gate_a_false_safe_rate"),
            }
        ],
    }
