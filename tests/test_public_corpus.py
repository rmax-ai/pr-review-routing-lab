from pathlib import Path

from review_lab.corpus import load_cases, load_gold, scan_paths
from review_lab.runner import Runner

ROOT = Path(__file__).parents[1]


def test_public_reconstructed_corpus_is_complete_and_clean():
    cases = load_cases(ROOT / "cases" / "public", public_only=True)
    assert len(cases) == 10
    assert [case.id for case in cases] == [
        "c01",
        "c02",
        "c03",
        "c04",
        "c05",
        "c06a",
        "c06b",
        "c07",
        "c08",
        "c09",
    ]
    assert scan_paths(ROOT / "cases" / "public") == []
    for case in cases:
        gold = load_gold(ROOT / "gold" / case.id / "expected.yaml")
        assert gold.case_id == case.id


def test_public_corpus_exercises_linked_and_dual_paths(tmp_path: Path):
    cases = load_cases(ROOT / "cases" / "public", public_only=True)
    selected = [case for case in cases if case.id in {"c06a", "c07", "c09"}]
    records = Runner(output_dir=tmp_path).run(
        selected,
        ["A3", "A4", "dual"],
        concurrency=2,
    )
    c06a = next(row for row in records if row.case_id == "c06a" and row.architecture == "A3")
    c07 = next(row for row in records if row.case_id == "c07" and row.architecture == "A4")
    c09 = next(row for row in records if row.case_id == "c09" and row.architecture == "dual")
    assert c06a.remediation_loops == 1
    assert c07.route.value == "human_review"
    assert any(stage.name == "dual_review" for stage in c09.stages)
