import ast
from pathlib import Path


def test_scoring_does_not_import_jev():
    tree = ast.parse(Path("src/review_lab/scoring.py").read_text(encoding="utf-8"))
    imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any(node.module and "jev" in node.module for node in imports)
