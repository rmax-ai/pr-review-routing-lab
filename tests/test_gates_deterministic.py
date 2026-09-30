from pathlib import Path

from review_lab.gates.deterministic import run_deterministic_gates


def test_completion_failure(tmp_path: Path):
    (tmp_path / "evidence.md").write_text("verified: true\nTODO: open", encoding="utf-8")
    rows = run_deterministic_gates(tmp_path, "+++ b/evidence.md\n")
    assert any(row.gate == "completion_state" and row.status == "fail" for row in rows)
