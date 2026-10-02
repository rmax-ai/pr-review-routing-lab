"""Arithmetic calibration and probability-breakpoint sweeps.

Outputs are demonstrations of calculation mechanics.  They intentionally do
not select a best threshold or make a calibration-quality claim.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Calibration:
    question: str
    n: int
    brier: float
    bins: tuple[dict[str, float | int], ...]
    claims: tuple[str, ...] = (
        "arithmetic demonstration only",
        "no calibration-quality claim",
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "n": self.n,
            "brier": self.brier,
            "bins": list(self.bins),
            "claims": list(self.claims),
        }


def _pairs(predictions: Iterable[float], truths: Iterable[bool]) -> list[tuple[float, bool]]:
    values = list(predictions)
    labels = list(truths)
    if len(values) != len(labels):
        raise ValueError("predictions and truths must have equal length")
    if any(not 0.0 <= float(value) <= 1.0 for value in values):
        raise ValueError("probabilities must be in [0,1]")
    if any(not isinstance(value, bool) for value in labels):
        raise ValueError("truths must be bool")
    return [(float(value), label) for value, label in zip(values, labels)]


def brier(predictions: Iterable[float], truths: Iterable[bool]) -> float:
    pairs = _pairs(predictions, truths)
    return (
        sum((prediction - int(truth)) ** 2 for prediction, truth in pairs) / len(pairs)
        if pairs
        else 0.0
    )


def reliability_bins(
    predictions: Sequence[float],
    truths: Sequence[bool],
    *,
    bins: int = 5,
) -> tuple[dict[str, float | int], ...]:
    if bins != 5:
        raise ValueError("the protocol uses exactly five reliability bins")
    pairs = _pairs(predictions, truths)
    rows: list[dict[str, float | int]] = []
    for bucket in range(bins):
        selected = [
            (prediction, truth)
            for prediction, truth in pairs
            if min(int(prediction * bins), bins - 1) == bucket
        ]
        rows.append(
            {
                "bin": bucket,
                "n": len(selected),
                "mean_predicted": (
                    sum(prediction for prediction, _ in selected) / len(selected)
                    if selected
                    else 0.0
                ),
                "empirical": (
                    sum(int(truth) for _, truth in selected) / len(selected) if selected else 0.0
                ),
            }
        )
    return tuple(rows)


def calibrate(
    question: str,
    predictions: list[float],
    truths: list[bool],
) -> Calibration:
    return Calibration(
        question=question,
        n=len(predictions),
        brier=brier(predictions, truths),
        bins=reliability_bins(predictions, truths),
    )


def sweep(
    predictions: list[float],
    truths: list[bool],
    *,
    breakpoints: Iterable[float] | None = None,
    step: float | None = None,
) -> list[dict[str, float | int | None]]:
    """Sweep distinct fixture probability breakpoints plus 0 and 1.

    Step-based sweeps are intentionally not part of the frozen protocol.
    """

    if step is not None:
        raise NotImplementedError("step-based calibration sweeps are not supported")
    pairs = _pairs(predictions, truths)
    values = {0.0, 1.0}
    values.update(float(value) for value in predictions)
    if breakpoints is not None:
        values.update(float(value) for value in breakpoints)
    thresholds = sorted(value for value in values if 0.0 <= value <= 1.0)
    rows: list[dict[str, float | int | None]] = []
    for threshold in thresholds:
        routed = [prediction >= threshold for prediction, _ in pairs]
        risky = [routed[index] and truth for index, (_, truth) in enumerate(pairs)]
        denominator = sum(routed)
        numerator = sum(risky)
        rows.append(
            {
                "threshold": threshold,
                "n": len(pairs),
                "route_count": denominator,
                "route_changes": sum(
                    1 for index in range(1, len(routed)) if routed[index] != routed[index - 1]
                ),
                "false_safe_numerator": numerator,
                "false_safe_denominator": denominator,
                "false_safe_rate": numerator / denominator if denominator else None,
            }
        )
    return rows


def route_changes(
    predictions: Sequence[float],
    thresholds: Iterable[float],
) -> list[dict[str, int | float]]:
    values = [float(item) for item in predictions]
    output = []
    previous: tuple[bool, ...] | None = None
    for threshold in sorted({float(item) for item in thresholds}):
        current = tuple(value >= threshold for value in values)
        output.append(
            {
                "threshold": threshold,
                "changed_cases": (
                    len(values)
                    if previous is None
                    else sum(old != new for old, new in zip(previous, current))
                ),
            }
        )
        previous = current
    return output


def aggregate(calibrations: Iterable[Calibration]) -> dict[str, float | int | str]:
    rows = list(calibrations)
    n = sum(row.n for row in rows)
    brier_score = sum(row.brier * row.n for row in rows) / n if n else 0.0
    return {
        "n": n,
        "brier": brier_score,
        "claims": "arithmetic demonstration only; no calibration-quality claim",
    }
