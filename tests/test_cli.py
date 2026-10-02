from review_lab.cli import main


def test_cli_cases_empty(tmp_path):
    assert main(["cases", "validate", "--root", str(tmp_path)]) == 0
