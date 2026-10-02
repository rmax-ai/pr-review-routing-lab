from pathlib import Path

import pytest

from review_lab.models import ReviewCase
from review_lab.runner import Runner


def test_runner_flushes_completed_records_and_resumes(tmp_path: Path, monkeypatch):
    cases = [ReviewCase(id="resume_a"), ReviewCase(id="resume_b")]
    runner = Runner(output_dir=tmp_path)
    original = runner.run_case
    calls = 0

    def abort_after_one(case, architecture):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected abort")
        return original(case, architecture)

    monkeypatch.setattr(runner, "run_case", abort_after_one)
    with pytest.raises(RuntimeError, match="injected abort"):
        runner.run(cases, ["A0"])

    records_path = tmp_path / "records.jsonl"
    first_bytes = records_path.read_bytes()
    assert len(first_bytes.splitlines()) == 1

    resumed = Runner(output_dir=tmp_path).run(cases, ["A0"])
    assert len(resumed) == 2
    second_bytes = records_path.read_bytes()
    assert len(second_bytes.splitlines()) == 2
    assert second_bytes.startswith(first_bytes)

    stable_bytes = second_bytes
    assert len(Runner(output_dir=tmp_path).run(cases, ["A0"])) == 2
    assert records_path.read_bytes() == stable_bytes
