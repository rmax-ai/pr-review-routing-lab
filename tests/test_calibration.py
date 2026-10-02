from review_lab.calibration import calibrate


def test_calibration_has_empty_bins():
    result = calibrate("q", [0.1, 0.9], [False, True])
    assert result.n == 2
    assert len(result.bins) == 5
