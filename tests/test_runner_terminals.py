from pathlib import Path

from review_lab.runner import Runner


def test_a4_no_sol_is_terminal(sample_case, tmp_path: Path):
    record = Runner(output_dir=tmp_path).run_case(
        sample_case, "A4", gate_a_questions={"needs_semantic_reasoning": False}
    )
    assert record.route.value == "accept_no_sol"
    assert record.jev_calls == 1
