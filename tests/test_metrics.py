from pathlib import Path

import yaml

from review_lab.metrics import benchmark_metrics, percentile
from review_lab.models import ReviewCase
from review_lab.runner import Runner


def test_percentile_is_empty_safe_and_deterministic():
    assert percentile([], 0.95) is None
    assert percentile([1, 2, 3, 4], 0.50) == 2.0
    assert percentile([1, 2, 3, 4], 0.95) == 4.0


def test_metric_builder_covers_registry_ids(tmp_path):
    records = Runner(output_dir=tmp_path).run(
        [ReviewCase(id="metrics_case")],
        ["A0"],
    )
    observed = {row["id"] for row in benchmark_metrics(records)}
    root = Path(__file__).parents[1]
    registry = yaml.safe_load((root / "configs" / "metrics.yaml").read_text())
    expected = {row["id"] for row in registry["metrics"]}
    assert observed == expected
