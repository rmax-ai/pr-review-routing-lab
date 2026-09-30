from review_lab.costing import money


def test_money_rounding():
    assert money("1.2345678") == "1.234568"
