from review_lab.harnesses.mock import MockHarness


def test_mock_harness_attests_fixture(tmp_path):
    verdict = MockHarness().run(tmp_path)
    assert verdict.fixture_provenance.endswith("used_gold:false")
