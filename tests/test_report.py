from pathlib import Path

import pytest

from review_lab.models import Route, RunRecord, Terminal
from review_lab.report import build_markdown, load_records, records_csv, verify_metric_registry


def _record(provenance: str = "synthetic_reconstructed") -> RunRecord:
    return RunRecord(
        run_id="report-row",
        case_ref="a" * 12,
        case_id="report_case",
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
        artifacts={"provenance": provenance},
    )


def test_load_records_reports_jsonl_path_and_line(tmp_path: Path):
    source = tmp_path / "records.jsonl"
    source.write_text("\nnot-json\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"records\.jsonl:2"):
        load_records(source)


def test_private_provenance_guard_covers_markdown_and_csv(tmp_path: Path):
    row = _record("private_replay")

    with pytest.raises(ValueError, match="private"):
        build_markdown([row])
    with pytest.raises(ValueError, match="private"):
        records_csv([row], tmp_path / "records.csv")


def test_metric_registry_skips_rows_without_id():
    assert verify_metric_registry([{"label": "not-a-metric"}, {"id": "needed"}], []) == [
        "needed"
    ]


def test_reports_publish_metric_numerator_and_denominator_values(tmp_path: Path):
    metric = {
        "id": "review_loops",
        "population": "linked_fixed_head_rows",
        "numerator": "real_re_review_artifacts",
        "denominator": "linked_fixed_head_rows",
        "numerator_value": 1,
        "denominator_value": 4,
        "value": 0.25,
    }

    markdown = build_markdown([_record()], metrics=[metric])
    assert "| review_loops | linked_fixed_head_rows | real_re_review_artifacts | linked_fixed_head_rows | 1 | 4 |" in markdown

    destination = tmp_path / "records.csv"
    records_csv([_record()], destination, metrics=[metric])
    csv_text = destination.read_text(encoding="utf-8")
    assert "numerator_value" in csv_text.splitlines()[0]
    assert ",metric,review_loops,linked_fixed_head_rows,real_re_review_artifacts,linked_fixed_head_rows,1,4,0.25,None" in csv_text


def test_reports_render_missing_metric_values_as_none(tmp_path: Path):
    destination = tmp_path / "records.csv"
    records_csv(
        [_record()],
        destination,
        metrics=[
            {
                "id": "blocker_recall",
                "population": "expected_blockers",
                "numerator": "matched_blockers",
                "denominator": "expected_blockers",
                "value": None,
            }
        ],
    )

    row = destination.read_text(encoding="utf-8").splitlines()[-1]
    assert (
        ",metric,blocker_recall,expected_blockers,matched_blockers,expected_blockers,"
        "None,None,None,None"
    ) in row


def test_example_report_publishes_fixed_head_loop_denominator():
    report = Path(__file__).parents[1] / "reports" / "example_mock.md"
    text = report.read_text(encoding="utf-8")

    assert (
        "| review_loops | linked_fixed_head_rows | real_re_review_artifacts | "
        "linked_fixed_head_rows | 0 | 7 | artifact | 0.0 |"
    ) in text
