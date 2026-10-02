from review_lab.gates.jev import JevAdapter


def test_mock_jev_is_deterministic():
    result = JevAdapter().evaluate("mock", "gate_a", {}, {"risk": True}, "case:gate_a")
    assert result.error is None
    assert result.answers[0].value is True
    assert result.usage.source.value == "simulated"
