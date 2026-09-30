from review_lab.digests import digest_model, digest_obj
from review_lab.gates.deterministic import run_deterministic_gates
from review_lab.models import ReviewCase, Route, RunRecord, StageRecord, Terminal
from review_lab.runner import Runner


def test_repeated_digest():
    value = {"case": "c", "answers": [1, 2]}
    assert digest_obj(value) == digest_obj(value)


def test_full_mock_runs_are_byte_identical(tmp_path, monkeypatch):
    monkeypatch.setenv("REVIEW_LAB_NOW", "2025-01-01T00:00:00+00:00")
    cases = [ReviewCase(id="det_a"), ReviewCase(id="det_b")]

    first = Runner(output_dir=tmp_path / "first").run(cases, ["A0", "A1", "A4"])
    second = Runner(output_dir=tmp_path / "second").run(cases, ["A0", "A1", "A4"])

    assert (tmp_path / "first" / "records.jsonl").read_bytes() == (
        tmp_path / "second" / "records.jsonl"
    ).read_bytes()
    assert [row.decision_digest for row in first] == [row.decision_digest for row in second]


def test_nested_stage_volatiles_are_excluded():
    def record(timestamp: str) -> RunRecord:
        return RunRecord(
            run_id="volatile",
            case_ref="a" * 12,
            case_id="volatile",
            case_digest="a" * 64,
            architecture="A0",
            stages=[
                StageRecord(
                    name="human_review",
                    started_at=timestamp,
                    ended_at=timestamp,
                    duration_ms=0,
                )
            ],
            route=Route.human_review,
            terminal=Terminal.routed_human,
            escalated=True,
            sol_invoked=False,
            jev_calls=0,
            remediation_loops=0,
            config_digest="b" * 64,
            backend="mock",
        )

    assert digest_model(record("2025-01-01T00:00:00+00:00")) == digest_model(
        record("2026-01-01T00:00:00+00:00")
    )


def test_security_boundary_skips_comments_and_filename_substrings(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "policy_notes.py").write_text("value = True\n", encoding="utf-8")
    patch = (
        "diff --git a/policy_notes.py b/policy_notes.py\n"
        "--- a/policy_notes.py\n"
        "+++ b/policy_notes.py\n"
        "@@ -1 +1,2 @@\n"
        " value = True\n"
        "+# policy is documented here\n"
    )
    security = next(
        item
        for item in run_deterministic_gates(repo, patch, ReviewCase(id="boundary"))
        if item.gate == "security_boundary"
    )

    assert security.status == "pass"


def test_expected_subject_without_declared_evidence_is_inconclusive(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    case = ReviewCase(id="missing_evidence", workstream_subject="subject", evidence_refs=["e.yaml"])

    evidence_binding = next(
        item
        for item in run_deterministic_gates(repo, "", case)
        if item.gate == "evidence_binding"
    )
    docs_only = next(
        item for item in run_deterministic_gates(repo, "", case) if item.gate == "docs_only"
    )

    assert evidence_binding.status == "inconclusive"
    assert docs_only.detail == "empty patch has no changed paths"
