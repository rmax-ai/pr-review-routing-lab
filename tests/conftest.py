import pytest

from review_lab.models import ReviewCase


@pytest.fixture
def sample_case() -> ReviewCase:
    return ReviewCase.model_validate_json(
        '{"id":"c01","title":"Evidence binding","failure_class":"evidence_binding",'
        '"description":"A toy change","requirements":[{"id":"R1","text":"bind evidence",'
        '"source":"issue","mandatory":true}],"base_ref":".","patch_ref":"change.patch",'
        '"author_lane":"codex","provenance":"synthetic_reconstructed","sanitization_note":"synthetic",'
        '"contracts_ref":"contracts.md"}'
    )
