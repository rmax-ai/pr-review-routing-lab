"""Architecture runner, invocation records, traces, and safe packet builder."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from .corpus import PrivateOverlayError, _reject_gold_path
from .digests import (
    case_digest,
    decision_digest,
    digest_obj,
    file_digest,
    file_set_digest,
    invocation_digest,
    observation_digest,
    packet_digest,
    verdict_digest,
)
from .gates.deterministic import run_deterministic_gates
from .gates.jev import JevAdapter
from .harnesses.base import ReviewerHarness
from .harnesses.mock import MockHarness, packet_files, verify_packet_manifest
from .models import (
    DataSource,
    EscalationDecision,
    GateDecision,
    GateId,
    InvocationRecord,
    ReviewCase,
    ReviewVerdict,
    Route,
    RunRecord,
    StageRecord,
    Terminal,
    UsageCost,
)
from .policies import (
    DEFAULT_THRESHOLDS,
    GATE_A_HARD_IDS,
    POLICY_VERSION,
    deterministic_policy,
    gate_a_policy,
    gate_b_policy,
    hard_rule_for,
)
from .question_sets import CANONICAL_QUESTION_IDS
from .util import is_path_under, now, write_json

ARCHITECTURES = ("A0", "A1", "A2", "A3", "A4", "A5", "dual")
PROMPT_TEMPLATE_DIGEST = digest_obj("review-packet-template-v2")


def _case_alias(case: ReviewCase) -> str:
    return case_digest(case)[:12].lower()


def _run_seed(
    case: ReviewCase,
    architecture: str,
    backend: str,
    model: str,
    effort: str,
    gate_a_questions: dict[str, Any] | None = None,
    gate_b_questions: dict[str, Any] | None = None,
) -> str:
    """Build a stable identity from every input that can affect a run."""

    if gate_a_questions is None and gate_b_questions is None:
        # Preserve the W1a identity for the default experiment command so
        # existing completed records remain resumable.
        return (
            f"{case_digest(case)}:{architecture}:{backend}:{model}:{effort}:"
            f"{case.linked_case_id or ''}"
        )
    return digest_obj(
        {
            "case": case_digest(case),
            "architecture": architecture,
            "backend": backend,
            "model": model,
            "effort": effort,
            "linked_case_id": case.linked_case_id or "",
            "gate_a_questions": gate_a_questions,
            "gate_b_questions": gate_b_questions,
        }
    )


def _fresh_run_id(output_dir: Path, base: str) -> str:
    """Avoid reusing directories left by an interrupted prior invocation."""

    candidate = base
    attempt = 0
    while (output_dir / candidate).exists():
        attempt += 1
        candidate = str(uuid5(NAMESPACE_URL, f"{base}:retry:{attempt}"))
    return candidate


class PacketBuilder:
    """Build the reviewer-safe packet and a hash manifest.

    The builder is intentionally independent of gold loading.  It accepts only
    a typed ``ReviewCase`` plus runtime evidence and rejects paths containing
    ``gold`` or files beginning with ``expected``.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def build(
        self,
        case: ReviewCase,
        evidence: list[Any],
        *,
        arm: str,
        patch: str = "",
        repo: str | Path | None = None,
        prior_review: Any | None = None,
        head_digest: str | None = None,
    ) -> Path:
        if not arm or Path(arm).name != arm or arm.startswith("."):
            raise ValueError("packet arm must be a contained identifier")
        if self.root.is_symlink():
            raise ValueError("packet root must not be a symlink")
        if case.provenance == "private_replay" and is_path_under(self.root, Path.cwd()):
            raise PrivateOverlayError("private packet outputs must be outside checkout")
        sources = [
            case.case_dir,
            case.base_ref,
            case.patch_ref,
            case.contracts_ref,
            case.prior_review_ref,
            *case.evidence_refs,
        ]
        for source in sources:
            if source:
                source_path = Path(str(source))
                if source != case.case_dir and (
                    "\\" in str(source) or source_path.is_absolute() or ".." in source_path.parts
                ):
                    raise ValueError("packet source path must be relative")
                _reject_gold_path(source_path)
                if source_path.name.lower().startswith("expected"):
                    raise ValueError("expected files are forbidden in reviewer packets")
        if repo is not None:
            _reject_gold_path(Path(repo))
        alias = _case_alias(case)
        destination = self.root / f"{alias}-{arm}"
        if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
            raise ValueError("packet destination must be fresh")
        destination.mkdir(parents=True, exist_ok=True)
        # Only these names are ever written.
        safe_case = {
            "case_ref": alias,
            "title": "Change under review",
            "base_ref": "repo",
            "case_digest": case_digest(case),
            "head_digest": head_digest or case.head_digest or digest_obj({}),
        }
        write_json(destination / "case.json", safe_case)
        write_json(
            destination / "deterministic_evidence.json",
            [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in evidence
            ],
        )
        requirements_lines = ["requirements:"]
        for requirement in sorted(case.requirements, key=lambda item: item.id):
            requirements_lines.extend(
                [
                    f"  - id: {requirement.id}",
                    f"    text: {json.dumps(requirement.text, ensure_ascii=False)}",
                    f"    source: {requirement.source.value}",
                    f"    mandatory: {'true' if requirement.mandatory else 'false'}",
                    f"    expects_marker: {'true' if requirement.expects_marker else 'false'}",
                ]
            )
        (destination / "requirements.yaml").write_text(
            "\n".join(requirements_lines) + "\n", encoding="utf-8"
        )
        contract_text = "Contract excerpt unavailable."
        contracts = case.contracts_ref
        contract_path = Path(str(contracts))
        if repo is not None:
            candidate = Path(repo).parent / contract_path
            if candidate.is_file():
                contract_text = candidate.read_text(encoding="utf-8")
        elif case.case_dir:
            candidate = Path(case.case_dir) / contract_path
            if candidate.is_file():
                contract_text = candidate.read_text(encoding="utf-8")
        (destination / "contracts.md").write_text(
            "# Review contracts\n\n" + contract_text + "\n", encoding="utf-8"
        )
        (destination / "change.patch").write_text(patch, encoding="utf-8")
        if repo is not None:
            source = Path(repo).resolve()
            if not source.is_dir() or source.is_symlink():
                raise ValueError("repository snapshot must be a non-symlink directory")
            if is_path_under(source, destination):
                raise ValueError("repository snapshot cannot be inside packet")
            for path in source.rglob("*"):
                if path.is_symlink():
                    raise ValueError("symlink repository entries are refused")
                if path.is_file() and (
                    "gold" in {part.lower() for part in path.parts}
                    or path.name.lower().startswith("expected")
                ):
                    raise ValueError("gold input is forbidden")
            shutil.copytree(
                source,
                destination / "repo",
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(".git"),
            )
        if case.evidence_refs:
            evidence_root = Path(case.case_dir) if case.case_dir else Path.cwd()
            for reference in case.evidence_refs:
                relative = Path(reference)
                if "\\" in str(relative) or relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("evidence reference must be relative")
                source = evidence_root / relative
                if (
                    not is_path_under(source, evidence_root)
                    or source.is_symlink()
                    or not source.is_file()
                ):
                    raise ValueError("evidence reference must name a regular file")
                _reject_gold_path(relative)
                manifest_entry = next(
                    (item for item in case.case_manifest if item.relative_path == str(relative)),
                    None,
                )
                if manifest_entry is not None and file_digest(source) != manifest_entry.sha256:
                    raise ValueError("evidence reference digest does not match case manifest")
                target = destination / "evidence" / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        if prior_review is not None:
            if isinstance(prior_review, (dict, list)):
                text = json.dumps(prior_review, sort_keys=True)
            else:
                text = str(prior_review)
            if any(
                marker in text.casefold()
                for marker in ("expected_findings", "human_required", "question_labels")
            ):
                raise ValueError("prior review contains adjudication fields")
            (destination / "prior_review.yaml").write_text(text, encoding="utf-8")
        for path in destination.rglob("*"):
            if path.is_file() and (
                "gold" in {part.casefold() for part in path.parts}
                or path.name.casefold().startswith("expected")
            ):
                raise ValueError("gold input is forbidden in reviewer packets")
        files = packet_files(destination)
        manifest = {
            "files": files,
            "packet_digest": packet_digest(files, PROMPT_TEMPLATE_DIGEST),
            "prompt_template_digest": PROMPT_TEMPLATE_DIGEST,
        }
        write_json(destination / "packet_manifest.json", manifest)
        return destination

    @staticmethod
    def verify(packet: str | Path) -> bool:
        return verify_packet_manifest(packet)


class Runner:
    def __init__(
        self,
        *,
        output_dir: str | Path = "runs",
        backend: str = "mock",
        jev: JevAdapter | None = None,
        harness: ReviewerHarness | None = None,
        model: str = "gpt-6-sol",
        effort: str = "low",
    ):
        if backend not in {"mock", "live"}:
            raise ValueError("backend must be mock or live")
        self.output_dir = Path(output_dir)
        self.backend = backend
        self.jev = jev or JevAdapter(raw_dir=self.output_dir / "raw")
        self.harness = harness or MockHarness()
        self.model = model
        self.effort = effort

    def _source_paths(
        self,
        case: ReviewCase,
        repo: str | Path | None,
        patch: str,
    ) -> tuple[Path, str]:
        if repo is not None:
            repo_path = Path(repo)
        elif case.case_dir:
            repo_path = Path(case.case_dir) / case.base_ref
        else:
            repo_path = Path(case.base_ref)
            if str(repo_path) in {".", "repo"}:
                repo_path = self.output_dir / "inputs" / case.id
                repo_path.mkdir(parents=True, exist_ok=True)
        if not repo_path.exists():
            raise ValueError("repository snapshot is missing")
        if patch:
            patch_text = patch
        elif case.case_dir and (Path(case.case_dir) / case.patch_ref).exists():
            patch_text = (Path(case.case_dir) / case.patch_ref).read_text(encoding="utf-8")
        elif Path(case.patch_ref).exists():
            patch_text = Path(case.patch_ref).read_text(encoding="utf-8")
        else:
            patch_text = ""
        return repo_path, patch_text

    def _analysis_repo(
        self,
        run_id: str,
        case: ReviewCase,
        repo: Path,
        patch: str,
    ) -> Path:
        if case.case_dir:
            head = Path(case.case_dir) / "head"
            if head.is_dir():
                return head
        if not patch.strip():
            return repo
        if repo.is_symlink() or any(path.is_symlink() for path in repo.rglob("*")):
            raise ValueError("repository snapshot contains a symlink")
        destination = self.output_dir / run_id / "applied_head"
        if destination.exists():
            raise ValueError("applied-head destination already exists")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            repo,
            destination,
            ignore=shutil.ignore_patterns(".git"),
        )
        for check_only in (True, False):
            command = ["git", "apply"]
            if check_only:
                command.append("--check")
            command.append("-")
            completed = subprocess.run(
                command,
                cwd=destination,
                input=patch,
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode:
                raise ValueError("change.patch does not apply to applied head")
        return destination

    @staticmethod
    def _questions(
        case: ReviewCase,
        gate: str,
        supplied: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if supplied:
            return supplied
        canonical = sorted(CANONICAL_QUESTION_IDS[gate])
        return {
            "ok": True,
            "answers": [
                {
                    "id": question,
                    "type": "boolean",
                    "value": False,
                    "probabilities": {"true": 0.0, "false": 1.0},
                }
                for question in canonical
            ],
            "usage": {},
        }

    def _config_digest(self, architecture: str) -> str:
        return digest_obj(
            {
                "architecture": architecture,
                "policy_version": POLICY_VERSION,
                "model": self.model,
                "effort": self.effort,
                "thresholds": DEFAULT_THRESHOLDS,
                "gate_a_hard_ids": sorted(GATE_A_HARD_IDS),
                "pricing": {
                    "gpt-6-sol": {
                        "input_usd_per_token": "0.000001",
                        "output_usd_per_token": "0.000003",
                    }
                },
                "questions": {
                    "gate_a": sorted(CANONICAL_QUESTION_IDS["gate_a"]),
                    "gate_b": sorted(CANONICAL_QUESTION_IDS["gate_b"]),
                },
            }
        )

    def _stage(self, name: str, data: dict[str, Any] | None = None) -> StageRecord:
        timestamp = now().isoformat()
        return StageRecord(
            name=name, started_at=timestamp, ended_at=timestamp, duration_ms=0, data=data or {}
        )

    def _jev_call(
        self,
        *,
        case: ReviewCase,
        head: str,
        packet: str,
        architecture: str,
        gate: str,
        questions: dict[str, Any],
        evidence_digest: str,
        config: str,
    ) -> tuple[Any, InvocationRecord]:
        prompt_digest = digest_obj(
            {
                "gate": gate,
                "questions": questions,
                "evidence_digest": evidence_digest,
                "architecture": architecture,
            }
        )
        invocation = InvocationRecord(
            case_digest=case_digest(case),
            head_digest=head,
            packet_digest=packet,
            prompt_digest=prompt_digest,
            config_digest=config,
            backend=self.backend,
            model="jev",
            fixture_version="mock-v1" if self.backend == "mock" else "live",
            invocation_digest=invocation_digest(
                case_digest_value=case_digest(case),
                head_digest_value=head,
                packet_digest_value=packet,
                prompt_digest=prompt_digest,
                config_digest=config,
                backend=self.backend,
                model="jev",
                fixture_version="mock-v1" if self.backend == "mock" else "live",
            ),
        )
        adapter = self.jev
        if isinstance(adapter, JevAdapter) and adapter.fixture_root is None and case.case_dir:
            adapter = JevAdapter(
                fixture_root=Path(case.case_dir) / "fixtures",
                raw_dir=self.output_dir / "raw",
            )
        question_payload = questions
        if (
            isinstance(question_payload, dict)
            and question_payload.get("ok") is True
            and not any(
                key in question_payload for key in ("case_digest", "head_digest", "packet_digest")
            )
        ):
            question_payload = {
                **question_payload,
                "case_digest": invocation.case_digest,
                "head_digest": invocation.head_digest,
                "packet_digest": invocation.packet_digest,
            }
        result = adapter.evaluate(
            self.backend,
            gate,
            {
                "case_digest": invocation.case_digest,
                "head_digest": invocation.head_digest,
                "packet_digest": invocation.packet_digest,
                "evidence_digest": evidence_digest,
                "architecture": architecture,
            },
            question_payload,
            f"{_case_alias(case)}:{case.id}:{architecture}:{gate}",
        )
        return result, invocation

    def _build_packet(
        self,
        run_id: str,
        case: ReviewCase,
        architecture: str,
        evidence: list[Any],
        patch: str,
        repo: Path,
        head: str,
    ) -> Path:
        prior_review: str | None = None
        if case.case_dir and case.prior_review_ref:
            path = Path(case.case_dir) / case.prior_review_ref
            if path.exists():
                prior_review = path.read_text(encoding="utf-8")
        return PacketBuilder(self.output_dir / run_id / "packets").build(
            case,
            evidence,
            arm=architecture,
            patch=patch,
            repo=repo,
            head_digest=head,
            prior_review=prior_review,
        )

    def _run_reviewer(
        self,
        case: ReviewCase,
        packet: Path,
        *,
        lane: str | None = None,
        architecture: str = "A4",
    ) -> ReviewVerdict:
        harness = self.harness
        if lane and isinstance(harness, MockHarness):
            from .models import HarnessId

            fixture = harness.fixture
            if fixture is None and case.case_dir:
                fixture_root = Path(case.case_dir) / "fixtures" / "reviewer"
                candidates = [
                    fixture_root / f"{architecture}_{lane}.json",
                    fixture_root / f"{lane}.json",
                    fixture_root / f"{architecture}.json",
                ]
                fixture = next((candidate for candidate in candidates if candidate.exists()), None)
            harness = MockHarness(fixture, HarnessId(lane))
        elif isinstance(harness, MockHarness) and harness.fixture is None and case.case_dir:
            candidate = Path(case.case_dir) / "fixtures" / "reviewer" / f"{architecture}.json"
            if candidate.exists():
                harness = MockHarness(candidate)
        return harness.run(packet, model=self.model, effort=self.effort)

    def _reviewer_invocation(
        self,
        case: ReviewCase,
        packet: Path,
        architecture: str,
        head: str,
        config: str,
    ) -> InvocationRecord:
        packet_value = packet_digest(packet_files(packet), PROMPT_TEMPLATE_DIGEST)
        prompt_value = digest_obj(
            {
                "case_digest": case_digest(case),
                "head_digest": head,
                "packet_digest": packet_value,
                "model": self.model,
                "effort": self.effort,
                "architecture": architecture,
            }
        )
        fixture_version = "mock-v1" if self.backend == "mock" else "live"
        return InvocationRecord(
            case_digest=case_digest(case),
            head_digest=head,
            packet_digest=packet_value,
            prompt_digest=prompt_value,
            config_digest=config,
            backend=self.backend,
            model=self.model,
            fixture_version=fixture_version,
            invocation_digest=invocation_digest(
                case_digest_value=case_digest(case),
                head_digest_value=head,
                packet_digest_value=packet_value,
                prompt_digest=prompt_value,
                config_digest=config,
                backend=self.backend,
                model=self.model,
                fixture_version=fixture_version,
            ),
        )

    def run_case(
        self,
        case: ReviewCase,
        architecture: str,
        *,
        patch: str = "",
        repo: str | Path | None = None,
        gate_a_questions: dict[str, Any] | None = None,
        gate_b_questions: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> RunRecord:
        architecture = architecture if architecture == "dual" else architecture.upper()
        if architecture not in ARCHITECTURES:
            raise ValueError(f"unknown architecture: {architecture}")
        if case.provenance == "private_replay" and is_path_under(self.output_dir, Path.cwd()):
            raise PrivateOverlayError("private outputs must be outside checkout")
        cdigest = case_digest(case)
        run_id = run_id or str(
            uuid5(
                NAMESPACE_URL,
                _run_seed(
                    case,
                    architecture,
                    self.backend,
                    self.model,
                    self.effort,
                    gate_a_questions,
                    gate_b_questions,
                ),
            )
        )
        if (self.output_dir / run_id).exists():
            run_id = _fresh_run_id(self.output_dir, run_id)
        stages: list[StageRecord] = []
        usage: list[UsageCost] = []
        invocations: list[InvocationRecord] = []
        head = case.head_digest or digest_obj({})
        sol_invoked = False
        try:
            repo_path, patch_text = self._source_paths(case, repo, patch)
            analysis_repo = self._analysis_repo(run_id, case, repo_path, patch_text)
            actual_head = file_set_digest(analysis_repo)
            expected_head = case.expected_head_digest or case.head_digest
            if expected_head and actual_head != expected_head:
                raise ValueError("applied head does not match expected digest")
            head = actual_head
            evidence = run_deterministic_gates(analysis_repo, patch_text, case)
            stages.append(
                self._stage(
                    "deterministic_gates",
                    {"evidence": [item.model_dump(mode="json") for item in evidence]},
                )
            )
            evidence_binding_digest = next(
                (
                    item.evidence_digest
                    for item in evidence
                    if item.gate == "evidence_binding"
                ),
                None,
            )
            if evidence_binding_digest is None:
                raise ValueError("deterministic evidence is missing evidence_binding")
            det = deterministic_policy(evidence)
            config = self._config_digest(architecture)
            if det.route == Route.deterministic_reject:
                return self._record(
                    run_id,
                    case,
                    architecture,
                    Route.deterministic_reject,
                    Terminal.det_rejected,
                    stages,
                    usage,
                    cdigest,
                    head,
                    False,
                    0,
                    config,
                    invocations,
                )
            if architecture == "A0":
                usage.append(
                    UsageCost(
                        source=DataSource.simulated
                        if self.backend == "mock"
                        else DataSource.measured,
                        component="human",
                        latency_ms=0,
                        usage_source="unavailable",
                    )
                )
                stages.append(self._stage("human_review"))
                return self._record(
                    run_id,
                    case,
                    architecture,
                    Route.human_review,
                    Terminal.routed_human,
                    stages,
                    usage,
                    cdigest,
                    head,
                    False,
                    0,
                    config,
                    invocations,
                )
            if any(item.status == "inconclusive" for item in evidence):
                return self._record(
                    run_id,
                    case,
                    architecture,
                    Route.human_review,
                    Terminal.routed_human,
                    stages,
                    usage,
                    cdigest,
                    head,
                    False,
                    0,
                    config,
                    invocations,
                )

            packet: Path | None = None
            verdict: ReviewVerdict | None = None
            lane: str | None = None
            if architecture == "A5":
                lane = "mock_droid" if case.author_lane == "codex" else "mock_codex"
            if architecture == "dual":
                lane = "mock_droid" if case.author_lane == "codex" else "mock_codex"

            def reviewer() -> ReviewVerdict:
                nonlocal packet, sol_invoked
                if packet is None:
                    packet = self._build_packet(
                        run_id, case, architecture, evidence, patch_text, analysis_repo, head
                    )
                sol_invoked = True
                reviewer_invocation = self._reviewer_invocation(
                    case, packet, architecture, head, config
                )
                invocations.append(reviewer_invocation)
                value = self._run_reviewer(case, packet, lane=lane, architecture=architecture)
                stages.append(
                    self._stage(
                        "sol_review",
                        {
                            "harness": value.harness.value,
                            "verdict_digest": verdict_digest(value),
                            "packet": str(packet.relative_to(self.output_dir / run_id)),
                            "invocation_digest": reviewer_invocation.invocation_digest,
                            "prompt_digest": reviewer_invocation.prompt_digest,
                        },
                    )
                )
                verdict_dir = self.output_dir / run_id / "verdicts"
                verdict_dir.mkdir(parents=True, exist_ok=True)
                (verdict_dir / f"{case.id}-{architecture}.json").write_text(
                    value.model_dump_json() + "\n", encoding="utf-8"
                )
                if value.usage:
                    if architecture == "dual":
                        usage.append(
                            UsageCost.model_validate_json(
                                json.dumps(
                                    {
                                        **value.usage.model_dump(mode="json"),
                                        "component": "dual_review",
                                    }
                                )
                            )
                        )
                    else:
                        usage.append(value.usage)
                return value

            # A1/A3 always invoke the reviewer.  A4/A5/dual invoke it only
            # after Gate A says so (or the deterministic floor says so).
            if architecture in {"A1", "A3"}:
                verdict = reviewer()

            gate_a_result = None
            gate_a_decision = None
            if architecture in {"A2", "A4", "A5", "dual"}:
                if packet is None:
                    packet = self._build_packet(
                        run_id, case, architecture, evidence, patch_text, analysis_repo, head
                    )
                gate_a_result, invocation = self._jev_call(
                    case=case,
                    head=head,
                    packet=packet_digest(packet_files(packet), PROMPT_TEMPLATE_DIGEST),
                    architecture=architecture,
                    gate="gate_a",
                    questions=self._questions(case, "gate_a", gate_a_questions),
                    evidence_digest=evidence_binding_digest,
                    config=config,
                )
                invocations.append(invocation)
                if gate_a_result.usage:
                    usage.append(gate_a_result.usage)
                gate_a_policy_result = gate_a_policy(
                    gate_a_result.answers,
                    deterministic_floor=det.route == Route.sol_review,
                    error=gate_a_result.error,
                )
                gate_a_decision = GateDecision(
                    gate=GateId.gate_a,
                    case_digest=cdigest,
                    head_digest=head,
                    evidence_digest=evidence_binding_digest,
                    route=gate_a_policy_result.route,
                    answers=gate_a_result.answers,
                    policy_version=POLICY_VERSION,
                    rationale=gate_a_policy_result.rationale,
                    error=gate_a_result.error,
                )
                stages.append(
                    self._stage(
                        "gate_a",
                        {
                            "decision": gate_a_decision.model_dump(mode="json"),
                            "invocation_digest": invocation.invocation_digest,
                            "prompt_digest": invocation.prompt_digest,
                        },
                    )
                )
                if gate_a_result.error:
                    return self._record(
                        run_id,
                        case,
                        architecture,
                        Route.human_review,
                        Terminal.error_terminal,
                        stages,
                        usage,
                        cdigest,
                        head,
                        sol_invoked,
                        0,
                        config,
                        invocations,
                        error=gate_a_result.error,
                    )
                elif gate_a_policy_result.route == Route.accept_no_sol:
                    if architecture == "A2":
                        return self._record(
                            run_id,
                            case,
                            architecture,
                            Route.human_review,
                            Terminal.routed_human,
                            stages,
                            usage,
                            cdigest,
                            head,
                            False,
                            0,
                            config,
                            invocations,
                        )
                    return self._record(
                        run_id,
                        case,
                        architecture,
                        Route.accept_no_sol,
                        Terminal.accept_no_sol,
                        stages,
                        usage,
                        cdigest,
                        head,
                        False,
                        0,
                        config,
                        invocations,
                    )
                elif verdict is None:
                    verdict = reviewer()

            dual_disagreement = False
            if architecture == "dual" and case.risk == "high" and verdict is not None:
                second_packet = packet or self._build_packet(
                    run_id, case, architecture, evidence, patch_text, analysis_repo, head
                )
                second_invocation = self._reviewer_invocation(
                    case, second_packet, architecture, head, config
                )
                invocations.append(second_invocation)
                second = self._run_reviewer(
                    case,
                    second_packet,
                    lane="mock_codex" if lane == "mock_droid" else "mock_droid",
                    architecture=architecture,
                )
                stages.append(
                    self._stage(
                        "dual_review",
                        {
                            "harness": second.harness.value,
                            "verdict_digest": verdict_digest(second),
                            "agreement": verdict_digest(second) == verdict_digest(verdict),
                            "error": second.error,
                            "invocation_digest": second_invocation.invocation_digest,
                            "prompt_digest": second_invocation.prompt_digest,
                        },
                    )
                )
                if second.usage:
                    usage.append(
                        UsageCost.model_validate_json(
                            json.dumps(
                                {
                                    **second.usage.model_dump(mode="json"),
                                    "component": "dual_review",
                                }
                            )
                        )
                    )
                dual_disagreement = verdict_digest(second) != verdict_digest(verdict)
                if second.error:
                    return self._record(
                        run_id,
                        case,
                        architecture,
                        Route.human_review,
                        Terminal.error_terminal,
                        stages,
                        usage,
                        cdigest,
                        head,
                        sol_invoked,
                        0,
                        config,
                        invocations,
                        error=second.error,
                    )
                if dual_disagreement:
                    return self._record(
                        run_id,
                        case,
                        architecture,
                        Route.human_review,
                        Terminal.routed_human,
                        stages,
                        usage,
                        cdigest,
                        head,
                        sol_invoked,
                        0,
                        config,
                        invocations,
                    )

            if verdict is None:
                verdict = reviewer()
            if verdict.error:
                return self._record(
                    run_id,
                    case,
                    architecture,
                    Route.human_review,
                    Terminal.error_terminal,
                    stages,
                    usage,
                    cdigest,
                    head,
                    sol_invoked,
                    0,
                    config,
                    invocations,
                    error=verdict.error,
                )

            if architecture in {"A3", "A4", "A5", "dual"}:
                gate_b_result, invocation = self._jev_call(
                    case=case,
                    head=head,
                    packet=packet_digest(packet_files(packet), PROMPT_TEMPLATE_DIGEST),
                    architecture=architecture,
                    gate="gate_b",
                    questions=self._questions(case, "gate_b", gate_b_questions),
                    evidence_digest=evidence_binding_digest,
                    config=config,
                )
                invocations.append(invocation)
                if gate_b_result.usage:
                    usage.append(gate_b_result.usage)
                hard_rule = hard_rule_for(
                    case,
                    evidence,
                    reviewer_error=verdict.error,
                    reviewer_blocker=any(
                        item.severity.value == "blocker" for item in verdict.findings
                    ),
                )
                gate_b_result_policy = gate_b_policy(
                    gate_b_result.answers, hard_rule=hard_rule, error=gate_b_result.error
                )
                gate_b_decision = EscalationDecision(
                    gate=GateId.gate_b,
                    case_digest=cdigest,
                    verdict_digest=verdict_digest(verdict),
                    route=gate_b_result_policy.route,
                    answers=gate_b_result.answers,
                    policy_version=POLICY_VERSION,
                    rationale=gate_b_result_policy.rationale,
                    hard_rule=gate_b_result_policy.hard_rule,
                    error=gate_b_result.error,
                )
                stages.append(
                    self._stage(
                        "gate_b",
                        {
                            "decision": gate_b_decision.model_dump(mode="json"),
                            "invocation_digest": invocation.invocation_digest,
                            "prompt_digest": invocation.prompt_digest,
                        },
                    )
                )
                route = gate_b_result_policy.route
                if gate_b_result.error:
                    terminal = Terminal.error_terminal
                elif verdict.verdict == "human_decision":
                    route = Route.human_review
                    terminal = Terminal.routed_human
                elif route == Route.remediate_simulated and verdict.verdict == "accept":
                    route = Route.accept
                    terminal = Terminal.sol_complete_accept
                elif route == Route.human_review:
                    terminal = Terminal.routed_human
                else:
                    terminal = Terminal.routed_remediate_simulated
                loops = (
                    1
                    if (
                        route == Route.remediate_simulated
                        and verdict.verdict == "changes_required"
                        and case.linked_case_id
                    )
                    else 0
                )
                if loops:
                    stages.append(
                        self._stage(
                            "remediation_loop",
                            {
                                "loop_index": 1,
                                "linked_case_id": case.linked_case_id,
                                "simulated": True,
                            },
                        )
                    )
                    usage.append(
                        UsageCost(
                            source=DataSource.simulated,
                            component="remediation_loop",
                            latency_ms=0,
                            usage_source="unavailable",
                        )
                    )
                return self._record(
                    run_id,
                    case,
                    architecture,
                    route,
                    terminal,
                    stages,
                    usage,
                    cdigest,
                    head,
                    sol_invoked,
                    loops,
                    config,
                    invocations,
                    error=gate_b_result.error,
                )

            if architecture == "A2":
                return self._record(
                    run_id,
                    case,
                    architecture,
                    Route.human_review,
                    Terminal.routed_human,
                    stages,
                    usage,
                    cdigest,
                    head,
                    sol_invoked,
                    0,
                    config,
                    invocations,
                )
            hard_rule = hard_rule_for(
                case,
                evidence,
                reviewer_error=verdict.error if verdict else None,
                reviewer_blocker=bool(
                    verdict and any(item.severity.value == "blocker" for item in verdict.findings)
                ),
            )
            if hard_rule and hard_rule != "security_boundary_floor":
                return self._record(
                    run_id,
                    case,
                    architecture,
                    Route.human_review,
                    Terminal.routed_human,
                    stages,
                    usage,
                    cdigest,
                    head,
                    sol_invoked,
                    0,
                    config,
                    invocations,
                )
            route = (
                Route.changes_required
                if verdict.verdict == "changes_required"
                else Route.human_review
                if verdict.verdict == "human_decision"
                else Route.accept
            )
            terminal = (
                Terminal.sol_complete_changes_required
                if route == Route.changes_required
                else Terminal.routed_human
                if route == Route.human_review
                else Terminal.sol_complete_accept
            )
            return self._record(
                run_id,
                case,
                architecture,
                route,
                terminal,
                stages,
                usage,
                cdigest,
                head,
                sol_invoked,
                0,
                config,
                invocations,
            )
        except PrivateOverlayError:
            raise
        except Exception:  # noqa: BLE001
            return self._record(
                run_id,
                case,
                architecture,
                Route.human_review,
                Terminal.error_terminal,
                stages,
                usage,
                cdigest,
                head,
                sol_invoked,
                0,
                self._config_digest(architecture),
                invocations,
                error="runner_error",
            )

    def _record(
        self,
        run_id: str,
        case: ReviewCase,
        architecture: str,
        route: Route,
        terminal: Terminal,
        stages: list[StageRecord],
        usage: list[UsageCost],
        cdigest: str,
        head: str,
        sol: bool,
        loops: int,
        config: str,
        invocations: list[InvocationRecord],
        error: str | None = None,
    ) -> RunRecord:
        if terminal == Terminal.routed_human and not any(
            stage.name == "human_review" for stage in stages
        ):
            stages.append(self._stage("human_review"))
        artifacts = {
            "case_digest": cdigest,
            "head_digest": head,
            "provenance": case.provenance,
        }
        record = RunRecord(
            run_id=run_id,
            case_ref=_case_alias(case),
            case_id=case.id,
            linked_case_id=case.linked_case_id,
            case_digest=cdigest,
            architecture=architecture,
            stages=stages,
            route=route,
            terminal=terminal,
            escalated=route in {Route.human_review, Route.sol_review},
            sol_invoked=sol,
            jev_calls=sum(item.model == "jev" for item in invocations),
            remediation_loops=loops,
            config_digest=config,
            prompt_digests={
                f"{stage.name}:{index}": str(stage.data["prompt_digest"])
                for index, stage in enumerate(stages)
                if stage.data.get("prompt_digest")
            },
            invocations=invocations,
            model_ids=list(dict.fromkeys(item.model for item in invocations)),
            backend=self.backend,
            usage=usage,
            artifacts=artifacts,
            error=error,
        )
        return record.model_copy(
            update={
                "decision_digest": decision_digest(record),
                "observation_digest": observation_digest(record),
                "invocation_digest": digest_obj(
                    sorted(item.invocation_digest or "" for item in invocations)
                ),
            }
        )

    def run(
        self,
        cases: Iterable[ReviewCase],
        architectures: Iterable[str],
        *,
        concurrency: int = 1,
    ) -> list[RunRecord]:
        if concurrency < 1:
            raise ValueError("concurrency must be positive")
        selected = []
        for architecture in architectures:
            value = architecture if architecture == "dual" else architecture.upper()
            if value not in ARCHITECTURES:
                raise ValueError(f"unknown architecture: {architecture}")
            if value not in selected:
                selected.append(value)
        jobs = [
            (case, architecture)
            for case in sorted(cases, key=lambda item: item.id)
            for architecture in selected
        ]
        self.output_dir.mkdir(parents=True, exist_ok=True)
        existing = self._load_persisted_records()
        existing_ids = {record.run_id for record in existing}
        existing_jobs = {
            (record.case_digest, record.architecture, record.backend) for record in existing
        }
        pending_jobs = [
            (case, architecture)
            for case, architecture in jobs
            if (
                str(
                    uuid5(
                        NAMESPACE_URL,
                        _run_seed(
                            case,
                            architecture,
                            self.backend,
                            self.model,
                            self.effort,
                        ),
                    )
                )
                not in existing_ids
                and (case_digest(case), architecture, self.backend) not in existing_jobs
            )
        ]

        failures: list[BaseException] = []
        if concurrency == 1:
            for case, architecture in pending_jobs:
                try:
                    record = self.run_case(case, architecture)
                except Exception as exc:  # noqa: BLE001
                    failures.append(exc)
                    break
                self._persist_record(record)
        else:
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = [
                    executor.submit(self.run_case, case, architecture)
                    for case, architecture in pending_jobs
                ]
                for future in as_completed(futures):
                    try:
                        record = future.result()
                    except Exception as exc:  # noqa: BLE001
                        failures.append(exc)
                        continue
                    self._persist_record(record)

        if failures:
            raise failures[0]
        return self._load_persisted_records()

    def _load_persisted_records(self) -> list[RunRecord]:
        path = self.output_dir / "records.jsonl"
        if not path.exists():
            return []
        records: list[RunRecord] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                records.append(RunRecord.model_validate_json(line))
            except Exception as exc:
                raise ValueError(f"invalid persisted record at line {line_number}") from exc
        return sorted(
            records,
            key=lambda record: (
                record.case_id or record.case_ref or "",
                record.architecture,
                record.run_id,
            ),
        )

    @staticmethod
    def _append_fsync(path: Path, text: str) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())

    def _persist_record(self, record: RunRecord) -> None:
        persisted = self._load_persisted_records()
        if record.run_id in {item.run_id for item in persisted}:
            return
        line = record.model_dump_json() + "\n"
        self._append_fsync(self.output_dir / "records.jsonl", line)
        with sqlite3.connect(self.output_dir / "run.db") as database:
            database.execute("PRAGMA synchronous=FULL")
            database.execute(
                """
                CREATE TABLE IF NOT EXISTS records (
                    run_id TEXT PRIMARY KEY,
                    record_json TEXT NOT NULL
                )
                """
            )
            database.execute(
                "INSERT OR IGNORE INTO records(run_id, record_json) VALUES (?, ?)",
                (record.run_id, record.model_dump_json()),
            )
            database.commit()
        record_dir = self.output_dir / record.run_id
        record_dir.mkdir(parents=True, exist_ok=True)
        (record_dir / "records.jsonl").write_text(line, encoding="utf-8")
        (record_dir / "invocations.jsonl").write_text(
            "\n".join(item.model_dump_json() for item in record.invocations) + "\n",
            encoding="utf-8",
        )
