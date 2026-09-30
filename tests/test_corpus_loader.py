from pathlib import Path

import pytest

from review_lab.corpus import CaseLoadError, build_manifest, load_case


def test_case_loader_rejects_gold(tmp_path: Path):
    (tmp_path / "case.yaml").write_text("gold: {}\n", encoding="utf-8")
    try:
        load_case(tmp_path)
    except ValueError as exc:
        assert "gold" in str(exc)
    else:
        raise AssertionError("gold leaked into reviewer case")


def test_fixture_gold_schema_is_rejected_structurally(tmp_path: Path):
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "review.json").write_text(
        '{"gold": {"expected_findings": []}, "used_gold": false}', encoding="utf-8"
    )

    with pytest.raises(CaseLoadError, match="gold schema"):
        build_manifest(tmp_path)
