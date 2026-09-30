"""Deterministic Markdown and CSV report builders."""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .models import RunRecord

TERMINAL_ROWS = [
    ("deterministic fail", "det_rejected"),
    ("Gate A no-Sol", "accept_no_sol"),
    ("Sol accepts", "sol_complete_accept"),
    ("Sol requests changes", "sol_complete_changes_required"),
    ("simulated remediation route", "routed_remediate_simulated"),
    ("human route", "routed_human"),
    ("error", "error_terminal"),
]


def load_records(path: str | Path) -> list[RunRecord]:
    source = Path(path)
    if source.is_dir():
        source = source / "records.jsonl"
    if not source.exists():
        raise FileNotFoundError(source)
    records = []
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except UnicodeError as exc:
        raise ValueError(f"{source}: invalid JSONL encoding") from exc
    for line_number, line in enumerate(lines, 1):
        if line.strip():
            try:
                records.append(RunRecord.model_validate_json(line))
            except Exception as exc:
                raise ValueError(f"{source}:{line_number}: invalid JSONL record") from exc
    return sorted(
        records,
        key=lambda record: (
            record.case_id or record.case_ref or "",
            record.architecture,
            record.run_id,
        ),
    )


def _caption(*, backend: str, source: str, n: int) -> str:
    if source == "mixed" or backend == "mixed":
        simulated = "mixed"
    else:
        simulated = "simulated" if source == "simulated" or backend == "mock" else "measured"
    return f"**Table (backend={backend}; source={source}; n={n}; {simulated}).**"


def records_csv(
    records: Iterable[RunRecord],
    destination: str | Path,
    *,
    metrics: Iterable[Mapping[str, Any]] | None = None,
) -> None:
    rows = sorted(
        records,
        key=lambda row: (row.case_id or row.case_ref or "", row.architecture, row.run_id),
    )
    if _has_private(rows):
        raise ValueError("reports refuse private provenance")
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "case",
                "architecture",
                "route",
                "terminal",
                "backend",
                "source",
                "simulated",
                "decision_digest",
                "row_type",
                "metric",
                "population",
                "numerator",
                "denominator",
                "numerator_value",
                "denominator_value",
                "value",
                "unavailable_reason",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "case": row.case_id or row.case_ref or "",
                    "architecture": row.architecture,
                    "route": row.route.value,
                    "terminal": row.terminal.value if row.terminal else "",
                    "backend": row.backend,
                    "source": "simulated" if row.backend == "mock" else "measured",
                    "simulated": "yes" if row.backend == "mock" else "no",
                    "decision_digest": row.decision_digest or "",
                    "row_type": "record",
                }
            )
        for metric in sorted(metrics or [], key=lambda item: str(item.get("id", ""))):
            writer.writerow(
                {
                    "row_type": "metric",
                    "metric": _csv_metric_value(metric.get("id")),
                    "population": _csv_metric_value(metric.get("population")),
                    "numerator": _csv_metric_value(metric.get("numerator")),
                    "denominator": _csv_metric_value(metric.get("denominator")),
                    "numerator_value": _csv_metric_value(metric.get("numerator_value")),
                    "denominator_value": _csv_metric_value(
                        metric.get("denominator_value")
                    ),
                    "value": _csv_metric_value(metric.get("value")),
                    "unavailable_reason": _csv_metric_value(
                        metric.get("unavailable_reason")
                    ),
                }
            )


def _csv_metric_value(value: Any) -> Any:
    """Keep explicit missing metric values visible in CSV output."""

    return "None" if value is None else value


def _has_private(records: list[RunRecord]) -> bool:
    return any(
        str(record.artifacts.get("provenance", "")) == "private_replay"
        or "private_replay" in str(record.artifacts)
        for record in records
    )


def verify_metric_registry(
    registry: Iterable[Mapping[str, Any]],
    observed_ids: Iterable[str],
) -> list[str]:
    required = {
        str(row["id"])
        for row in registry
        if isinstance(row, Mapping) and row.get("id") is not None
    }
    observed = set(observed_ids)
    return sorted(required - observed)


def build_markdown(
    records: Iterable[RunRecord],
    *,
    metrics: Iterable[Mapping[str, Any]] | None = None,
) -> str:
    rows = sorted(
        records,
        key=lambda row: (row.case_id or row.case_ref or "", row.architecture, row.run_id),
    )
    metric_rows = list(metrics or [])
    if _has_private(rows):
        raise ValueError("reports refuse private provenance")
    backend = (
        "mock"
        if all(row.backend == "mock" for row in rows)
        else "live"
        if all(row.backend == "live" for row in rows)
        else "mixed"
    )
    source = "simulated" if backend == "mock" else "measured" if backend == "live" else "mixed"
    mock_report = backend == "mock"
    title = "# Mock protocol demonstration" if mock_report else "# Review routing protocol report"
    introduction = (
        "This is a mechanics demonstration over simulated fixtures. It does not claim "
        "model quality, calibration quality, real cost savings, autonomy, or reviewer "
        "independence."
        if mock_report
        else "This report records routing protocol observations. It does not by itself "
        "establish model quality, calibration quality, cost savings, autonomy, or "
        "reviewer independence."
    )
    lines = [
        title,
        "",
        introduction,
        "",
        _caption(backend=backend, source=source, n=len(rows)),
        "| case | architecture | route | terminal | backend |",
        "|---|---|---|---|---|",
    ]
    lines.extend(
        "| {case} | {architecture} | {route} | {terminal} | {backend} |".format(
            case=row.case_id or row.case_ref or "",
            architecture=row.architecture,
            route=row.route.value,
            terminal=row.terminal.value if row.terminal else "",
            backend=row.backend,
        )
        for row in rows
    )
    no_claims = [
        "- This report makes no model-quality or calibration-quality claim.",
        "- Costs are not real savings and remediation is not autonomous.",
        "- A5 and dual reviewer lanes are wiring simulations, not independence claims.",
    ]
    if mock_report:
        no_claims.insert(
            0, "- Mock values are simulated mechanics drivers, not measured model outcomes."
        )
    lines.extend(
        [
            "",
            "## State-transition table",
            "",
            _caption(backend=backend, source=source, n=len(TERMINAL_ROWS)),
            "| transition | terminal |",
            "|---|---|",
        ]
    )
    lines.extend(f"| {label} | {terminal} |" for label, terminal in TERMINAL_ROWS)
    lines.extend(
        [
            "",
            "## Case × arm traces",
            "",
            _caption(backend=backend, source=source, n=len(rows)),
            "| case | arm | stages | decision digest |",
            "|---|---|---|---|",
        ]
    )
    lines.extend(
        "| {case} | {arm} | {stages} | {digest} |".format(
            case=row.case_id or row.case_ref or "",
            arm=row.architecture,
            stages=", ".join(stage.name for stage in row.stages) or "deterministic",
            digest=row.decision_digest or "",
        )
        for row in rows
    )
    lines.extend(
        [
            "",
            "## Metric-registry coverage",
            "",
            _caption(backend=backend, source=source, n=len(metric_rows)),
            "| metric | population | numerator | denominator | numerator_value | denominator_value | source | value | unavailable_reason |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for metric in sorted(metric_rows, key=lambda item: str(item.get("id", ""))):
        lines.append(
            "| {id} | {population} | {numerator} | {denominator} | {numerator_value} | {denominator_value} | {source} | {value} | {unavailable_reason} |".format(
                id=metric.get("id", ""),
                population=metric.get("population", ""),
                numerator=metric.get("numerator", ""),
                denominator=metric.get("denominator", ""),
                numerator_value=metric.get("numerator_value", ""),
                denominator_value=metric.get("denominator_value", ""),
                source=metric.get("source", ""),
                value=metric.get("value", ""),
                unavailable_reason=metric.get("unavailable_reason", ""),
            )
        )
    lines.extend(
        [
            "",
            "## No-claims section",
            "",
            *no_claims,
        ]
    )
    return "\n".join(lines) + "\n"


def build_report(
    records: Iterable[RunRecord],
    destination: str | Path,
    *,
    metrics: Iterable[Mapping[str, Any]] | None = None,
    csv_destination: str | Path | None = None,
) -> Path:
    rows = list(records)
    metric_rows = list(metrics or [])
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_markdown(rows, metrics=metric_rows), encoding="utf-8")
    if csv_destination is not None:
        records_csv(rows, csv_destination, metrics=metric_rows)
    return path


def report_bytes(
    records: Iterable[RunRecord], metrics: Iterable[Mapping[str, Any]] | None = None
) -> bytes:
    return build_markdown(records, metrics=metrics).encode("utf-8")
