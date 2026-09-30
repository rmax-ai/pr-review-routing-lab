import json
import sqlite3
from pathlib import Path

import pytest

from review_lab.corpus import load_case
from review_lab.digests import case_digest, file_set_digest
from review_lab.gates.jev import JevAdapter
from review_lab.models import Finding, GoldCase, ReviewCase
from review_lab.runner import PacketBuilder, Runner
from review_lab.scoring import score_verdict


def test_compact_jev_rejects_unregistered_questions():
    result = JevAdapter().evaluate("mock", "gate_a", {}, {"unregistered": True}, "case")
    assert result.error == "jev_schema_invalid"


def test_case_digest_attestation_is_stable(tmp_path: Path):
    (tmp_path / "repo").mkdir()
    (tmp_path / "head").mkdir()
    (tmp_path / "change.patch").write_text("", encoding="utf-8")
    metadata = {
        "id": "attested_case",
        "expected_head_digest": file_set_digest(tmp_path / "head"),
        "provenance": "public_source",
    }
    (tmp_path / "case.yaml").write_text(json.dumps(metadata), encoding="utf-8")
    first = load_case(tmp_path)
    digest = case_digest(first)
    metadata["expected_case_digest"] = digest
    (tmp_path / "case.yaml").write_text(json.dumps(metadata), encoding="utf-8")
    assert case_digest(load_case(tmp_path)) == digest


def test_packet_manifest_verifier_rejects_nested_manifest(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    packet = PacketBuilder(tmp_path / "packets").build(
        ReviewCase(id="packet_case"),
        [],
        arm="A1",
        repo=repo,
        head_digest="a" * 64,
    )
    nested = packet / "repo" / "packet_manifest.json"
    nested.write_text("tampered", encoding="utf-8")
    assert not PacketBuilder.verify(packet)


def test_score_verdict_unions_independent_coverage():
    gold = GoldCase.model_validate_json(
        '{"case_id":"coverage","expected_findings":[{"severity":"material",'
        '"defect_class":"other","requirement_refs":["R1"],'
        '"match":{"requirement_any":["R1"]}}],"human_required":false,'
        '"verdict_expectation":"changes_required","labeled_by":"operator"}'
    )
    finding = Finding.model_validate_json(
        '{"id":"F1","severity":"material","defect_class":"other",'
        '"evidence":"missing","confidence":0.8}'
    )
    verdict = {
        "case_id": "coverage",
        "case_digest": "a" * 64,
        "head_digest": "b" * 64,
        "packet_digest": "c" * 64,
        "verdict": "changes_required",
        "requirement_coverage": [
            {"requirement_id": "R1", "status": "addressed", "note": "covered"}
        ],
        "findings": [finding.model_dump(mode="json")],
        "unresolved_human_decisions": [],
        "model": "mock",
        "effort": "low",
        "harness": "mock_codex",
    }
    from review_lab.models import ReviewVerdict

    score = score_verdict(ReviewVerdict.model_validate_json(json.dumps(verdict)), gold)
    assert score.requirement_coverage_recall == 1.0


def test_runner_concurrency_writes_sqlite_mirror(tmp_path: Path):
    records = Runner(output_dir=tmp_path).run(
        [ReviewCase(id="parallel_case")],
        ["A0", "A1"],
        concurrency=2,
    )
    with sqlite3.connect(tmp_path / "run.db") as database:
        count = database.execute("SELECT count(*) FROM records").fetchone()[0]
    assert count == len(records)


def test_runner_rejects_nonpositive_concurrency(tmp_path: Path):
    with pytest.raises(ValueError, match="concurrency"):
        Runner(output_dir=tmp_path).run([], ["A0"], concurrency=0)
