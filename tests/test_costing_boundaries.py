import pytest

from review_lab.costing import UnpricedUsageError, sensitivity, usage_cost
from review_lab.models import DataSource, UsageCost


def test_available_unpriced_usage_is_typed():
    row = UsageCost(
        input_tokens=10,
        output_tokens=5,
        source=DataSource.measured,
        component="jev",
        model="unknown",
    )

    with pytest.raises(UnpricedUsageError):
        usage_cost([row])


def test_sensitivity_ranges_are_sorted():
    rows = sensitivity("1", {"threshold": [0.9, 0.1, 0.5]})

    assert [row["threshold"] for row in rows] == ["0.1", "0.5", "0.9"]
