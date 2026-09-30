from review_lab.models import Finding, GoldCase
from review_lab.scoring import score_findings


def test_finding_match():
    gold = GoldCase.model_validate_json(
        '{"case_id":"c","expected_findings":[{"severity":"material","defect_class":"other",'
        '"requirement_refs":["R1"],"match":{"requirement_any":["R1"]}}],"human_required":false,'
        '"verdict_expectation":"changes_required","labeled_by":"operator"}'
    )
    finding = Finding.model_validate_json(
        '{"id":"F","severity":"material","defect_class":"other","requirement_refs":["R1"],'
        '"evidence":"issue","confidence":0.8}'
    )
    assert score_findings([finding], gold).exact_matches == 1
