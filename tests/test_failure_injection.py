from pathlib import Path

import pytest
import yaml

from review_lab import runner as runner_module
from review_lab.gates import jev as jev_module
from review_lab.gates.deterministic import run_deterministic_gates
from review_lab.gates.jev import JevAdapter
from review_lab.harnesses.mock import MockHarness
from review_lab.models import ReviewCase
from review_lab.runner import PacketBuilder, Runner
from review_lab.util import BoundedProcessResult


def _packet(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    return PacketBuilder(tmp_path / "packets").build(
        ReviewCase(id="failure_case"),
        [],
        arm="A1",
        repo=repo,
        head_digest="a" * 64,
    )


def test_corrupt_packet_manifest_is_typed(tmp_path: Path):
    packet = _packet(tmp_path)
    (packet / "packet_manifest.json").write_text("{", encoding="utf-8")

    verdict = MockHarness().run(packet)

    assert verdict.error == "reviewer_packet_mutated"
    assert verdict.verdict == "human_decision"


@pytest.mark.parametrize(
    ("fixture", "error"),
    [
        ({"failure": "timeout"}, "reviewer_timeout"),
        ({"verdict": "not-a-verdict"}, "reviewer_invalid_verdict"),
    ],
)
def test_mock_reviewer_failures_are_typed(tmp_path: Path, fixture, error):
    verdict = MockHarness(fixture).run(_packet(tmp_path))

    assert verdict.error == error
    assert verdict.verdict == "human_decision"
    assert verdict.usage is not None
    assert verdict.usage.usage_source == "unavailable"


def test_jev_error_and_timeout_are_typed(tmp_path: Path, monkeypatch):
    invalid = JevAdapter().evaluate("mock", "gate_a", {}, {"unknown": True}, "case")
    assert invalid.error == "jev_schema_invalid"

    class FakeProcess:
        pid = 1
        returncode = None

        def poll(self):
            return None

    monkeypatch.setenv("REVIEW_LAB_JEV_BIN", "fake-jev")
    monkeypatch.setattr(jev_module.shutil, "which", lambda _: "/bin/fake-jev")
    monkeypatch.setattr(jev_module.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(
        jev_module,
        "communicate_bounded",
        lambda *args, **kwargs: BoundedProcessResult(b"", b"", True, False),
    )
    monkeypatch.setattr(jev_module, "_kill_process_group", lambda _: None)

    timed_out = JevAdapter(packet_workdir=tmp_path).evaluate(
        "live", "gate_a", {}, {}, "case", timeout_s=1000
    )

    assert timed_out.error == "jev_timeout"


def test_non_utf8_file_is_tolerated_per_file(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "binary.dat").write_bytes(b"\xff\xfe")
    evidence = run_deterministic_gates(repo, "", ReviewCase(id="binary_case"))

    assert any(item.status != "inconclusive" for item in evidence)
    assert next(item for item in evidence if item.gate == "docs_only").status == "informational"


def test_gate_a_error_does_not_invoke_reviewer(tmp_path: Path):
    class FailingJev:
        fixture_root = None

        def evaluate(self, *args, **kwargs):
            from review_lab.gates.jev import JevResult

            return JevResult([], None, error="jev_timeout")

    class ExplodingHarness(MockHarness):
        def run(self, *args, **kwargs):
            raise AssertionError("reviewer must not run after Gate A error")

    record = Runner(
        output_dir=tmp_path,
        jev=FailingJev(),
        harness=ExplodingHarness(),
    ).run_case(ReviewCase(id="gate_a_error"), "A4")

    assert record.terminal.value == "error_terminal"
    assert record.error == "jev_timeout"
    assert not any(stage.name == "sol_review" for stage in record.stages)


@pytest.mark.parametrize("failure", ["timeout", "invalid-verdict"])
def test_runner_emits_one_typed_reviewer_error(tmp_path: Path, failure: str):
    record = Runner(
        output_dir=tmp_path,
        harness=MockHarness({"failure": failure}),
    ).run_case(ReviewCase(id=f"runner_{failure.replace('-', '_')}"), "A1")

    assert record.terminal.value == "error_terminal"
    assert record.error in {"reviewer_timeout", "reviewer_invalid_verdict"}
    assert sum(stage.name == "sol_review" for stage in record.stages) == 1


@pytest.mark.parametrize("exception", [TypeError("mock"), yaml.YAMLError("fixture"), StopIteration()])
def test_runner_normalizes_unexpected_case_exceptions(
    tmp_path: Path, monkeypatch, exception: Exception
):
    def explode(*args, **kwargs):
        raise exception

    monkeypatch.setattr(runner_module, "run_deterministic_gates", explode)
    records = Runner(output_dir=tmp_path).run([ReviewCase(id="exception_case")], ["A0"])

    assert len(records) == 1
    assert records[0].terminal.value == "error_terminal"
    assert records[0].error == "runner_error"
