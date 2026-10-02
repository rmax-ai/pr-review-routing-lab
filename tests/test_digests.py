from review_lab.digests import digest_obj


def test_digest_is_canonical():
    assert digest_obj({"b": 2, "a": 1}) == digest_obj({"a": 1, "b": 2})
