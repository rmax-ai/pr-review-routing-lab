"""Pydantic v2 contracts for the offline review-routing benchmark.

The models in this module are deliberately boring.  They are the boundary between
case files, provider fixtures, run artifacts, and the analysis code, so accepting a
slightly malformed value here would make the benchmark appear more reproducible
than it is.
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from enum import StrEnum
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .question_sets import CANONICAL_QUESTION_IDS, LEGACY_GATE_A_IDS

HASH_RE = re.compile(r"^[0-9a-f]{64}$")
ALIAS_RE = re.compile(r"^[0-9a-f]{12}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
MONEY_RE = re.compile(r"^(?:0|[0-9]+)(?:\.[0-9]{1,12})?$")


class FrozenModel(BaseModel):
    """Strict immutable base for serialized values."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        validate_assignment=True,
    )


class Severity(StrEnum):
    blocker = "blocker"
    material = "material"
    minor = "minor"


class DefectClass(StrEnum):
    evidence_binding = "evidence_binding"
    completion_state = "completion_state"
    lifecycle_calibration = "lifecycle_calibration"
    retention_bound = "retention_bound"
    requirement_omission = "requirement_omission"
    security_boundary = "security_boundary"
    semantic_correctness = "semantic_correctness"
    docs_only_control = "docs_only_control"
    other = "other"


class Route(StrEnum):
    accept = "accept"
    accept_no_sol = "accept_no_sol"
    changes_required = "changes_required"
    sol_review = "sol_review"
    remediate_simulated = "remediate_simulated"
    human_review = "human_review"
    deterministic_reject = "deterministic_reject"


class Terminal(StrEnum):
    det_rejected = "det_rejected"
    accept_no_sol = "accept_no_sol"
    sol_complete_accept = "sol_complete_accept"
    sol_complete_changes_required = "sol_complete_changes_required"
    routed_remediate_simulated = "routed_remediate_simulated"
    routed_human = "routed_human"
    error_terminal = "error_terminal"


class GateId(StrEnum):
    gate_a = "gate_a"
    gate_b = "gate_b"


# Compatibility exports for callers of the initial scaffold.  The canonical
# registry lives in ``question_sets`` so every boundary uses the same IDs.
GATE_A_QUESTION_IDS = CANONICAL_QUESTION_IDS["gate_a"]
GATE_B_QUESTION_IDS = CANONICAL_QUESTION_IDS["gate_b"]


class HarnessId(StrEnum):
    codex = "codex"
    droid = "droid"
    mock_codex = "mock_codex"
    mock_droid = "mock_droid"


class DataSource(StrEnum):
    measured = "measured"
    simulated = "simulated"
    modeled = "modeled"


class RequirementSource(StrEnum):
    issue = "issue"
    review = "review"
    adr = "adr"
    policy = "policy"


class ErrorCode(StrEnum):
    """Stable machine error values.

    Dynamic exit codes are validated by the model validators below because their
    integer suffix is part of the useful diagnostic while the prefix is stable.
    """

    jev_binary_missing = "jev_binary_missing"
    jev_cap_refused = "jev_cap_refused"
    jev_schema_invalid = "jev_schema_invalid"
    jev_missing_answer = "jev_missing_answer"
    jev_distribution_invalid = "jev_distribution_invalid"
    jev_timeout = "jev_timeout"
    jev_audit_partial = "jev_audit_partial"
    reviewer_binary_missing = "reviewer_binary_missing"
    reviewer_timeout = "reviewer_timeout"
    reviewer_packet_mutated = "reviewer_packet_mutated"
    reviewer_invalid_verdict = "reviewer_invalid_verdict"
    invalid_record = "invalid_record"
    input_missing = "input_missing"
    input_invalid = "input_invalid"
    policy_refused = "policy_refused"
    runner_error = "runner_error"


def _validate_id(value: str) -> str:
    if not value or not ID_RE.fullmatch(value):
        raise ValueError("id must be a non-empty identifier")
    return value


def _validate_hash(value: str | None, *, allow_empty: bool = False) -> str | None:
    if value is None:
        return None
    if allow_empty and value == "":
        return value
    if not HASH_RE.fullmatch(value):
        raise ValueError("digest must be a lowercase SHA-256 hex string")
    return value


def _validate_money(value: str | None) -> str | None:
    if value is None:
        return value
    if not MONEY_RE.fullmatch(value):
        raise ValueError("money must be a non-negative decimal string")
    return value


def _validate_error_code(value: str | None) -> str | None:
    if value is None:
        return None
    known = {item.value for item in ErrorCode}
    if value in known:
        return value
    if re.fullmatch(r"jev_exit_-?[0-9]+", value):
        return value
    if re.fullmatch(r"reviewer_exit_-?[0-9]+", value):
        return value
    raise ValueError("error must be a registered typed error code")


class Requirement(FrozenModel):
    id: str
    text: str
    source: RequirementSource
    mandatory: bool
    expects_marker: bool = False
    surface: str | None = None
    marker: str | None = None

    _id = field_validator("id")(_validate_id)

    @field_validator("text")
    @classmethod
    def nonempty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("requirement text is required")
        return value


class Finding(FrozenModel):
    id: str
    severity: Severity
    defect_class: DefectClass
    requirement_refs: list[str] = Field(default_factory=list)
    evidence: str
    proposed_regression: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    location: str | None = None

    _id = field_validator("id")(_validate_id)

    @field_validator("requirement_refs")
    @classmethod
    def unique_refs(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("finding requirement_refs must be unique")
        for reference in value:
            _validate_id(reference)
        return value

    @field_validator("evidence")
    @classmethod
    def nonempty_evidence(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("finding evidence is required")
        return value


ReviewFinding = Finding


class CaseManifestEntry(FrozenModel):
    relative_path: str
    sha256: str
    role: Literal[
        "base",
        "target",
        "case_meta",
        "patch",
        "requirement",
        "contract",
        "evidence",
        "prior_review",
    ]

    _digest = field_validator("sha256")(_validate_hash)

    @field_validator("relative_path")
    @classmethod
    def safe_relative_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        if not value or normalized.startswith("/") or ".." in normalized.split("/"):
            raise ValueError("manifest paths must be relative and contained")
        return value


ManifestEntry = CaseManifestEntry


class DeterministicEvidence(FrozenModel):
    gate: str
    status: Literal["pass", "fail", "mandatory_review", "informational", "inconclusive"]
    detail: str
    input_hashes: dict[str, str] = Field(default_factory=dict)
    head_digest: str
    analyzer_version: str
    duration_ms: int = Field(default=0, ge=0)
    evidence_digest: str

    _head = field_validator("head_digest")(_validate_hash)
    _evidence = field_validator("evidence_digest")(_validate_hash)

    @field_validator("input_hashes")
    @classmethod
    def input_digests(cls, value: dict[str, str]) -> dict[str, str]:
        for digest in value.values():
            _validate_hash(digest)
        return dict(sorted(value.items()))

    @field_validator("gate")
    @classmethod
    def known_gate(cls, value: str) -> str:
        if value not in {
            "evidence_binding",
            "completion_state",
            "calibration_reset",
            "retention_bound",
            "requirement_markers",
            "exact_head_revision",
            "docs_only",
            "security_boundary",
        }:
            raise ValueError("unknown deterministic gate")
        return value


class QuestionAnswer(FrozenModel):
    id: str
    type: Literal["boolean", "choice", "score"]
    value: bool | str | float | None
    probabilities: dict[str, float]
    derived_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    cost_usd: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)

    _money = field_validator("cost_usd")(_validate_money)
    _id = field_validator("id")(_validate_id)

    @field_validator("probabilities", mode="before")
    @classmethod
    def normalize_probabilities(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            raise TypeError("probabilities must be an object")
        normalized: dict[str, float] = {}
        for key, item in value.items():
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                raise TypeError("probabilities must be numeric")
            normalized[str(key)] = float(item)
        return normalized

    @model_validator(mode="after")
    def validate_distribution(self) -> QuestionAnswer:
        if not self.id:
            raise ValueError("question id is required")
        if not self.probabilities:
            raise ValueError("probability distribution is required")
        if any(
            not math.isfinite(value) or value < 0.0 or value > 1.0
            for value in self.probabilities.values()
        ):
            raise ValueError("probabilities must be finite and in [0,1]")
        if abs(sum(self.probabilities.values()) - 1.0) > 1e-6:
            raise ValueError("probabilities must sum to one")
        if self.type == "boolean":
            if self.value is not None and not isinstance(self.value, bool):
                raise ValueError("boolean answers require bool or null")
            if set(self.probabilities) != {"true", "false"}:
                raise ValueError("boolean distributions need true and false")
            if self.value is not None:
                expected = 1.0 if self.value else 0.0
                if abs(self.probabilities["true"] - expected) > 1e-6:
                    raise ValueError("boolean value conflicts with probability distribution")
        elif self.type == "choice":
            if self.derived_confidence is None:
                raise ValueError("choice answers require derived_confidence")
            if self.value is not None and not isinstance(self.value, str):
                raise ValueError("choice answers require string or null")
        elif self.type == "score":
            if self.derived_confidence is None:
                raise ValueError("score answers require derived_confidence")
            if self.value is not None and (
                isinstance(self.value, bool) or not isinstance(self.value, float)
            ):
                raise ValueError("score answers require float or null")
        return self


class QuestionSpec(FrozenModel):
    id: str
    type: Literal["boolean", "choice", "score"] = "boolean"

    _id = field_validator("id")(_validate_id)


class QuestionSet(FrozenModel):
    id: GateId
    instructions: str
    questions: list[QuestionSpec]

    @model_validator(mode="after")
    def unique_question_ids(self) -> QuestionSet:
        ids = [question.id for question in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("question ids must be unique")
        expected = CANONICAL_QUESTION_IDS[self.id.value]
        if set(ids) != expected:
            raise ValueError("question set contains unknown or missing question ids")
        if any(question.type != "boolean" for question in self.questions):
            raise ValueError("registered gate questions must be boolean")
        return self


class UsageCost(FrozenModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    usd: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    source: DataSource
    component: Literal["jev", "sol_review", "human", "infra", "dual_review", "remediation_loop"]
    model: str | None = None
    usage_source: Literal["available", "unavailable"] = "available"

    _money = field_validator("usd")(_validate_money)


class GateDecision(FrozenModel):
    gate: GateId
    case_digest: str
    head_digest: str
    evidence_digest: str
    route: Route
    answers: list[QuestionAnswer] = Field(default_factory=list)
    policy_version: str
    rationale: str
    error: str | None = None

    _case = field_validator("case_digest")(_validate_hash)
    _head = field_validator("head_digest")(_validate_hash)
    _evidence = field_validator("evidence_digest")(_validate_hash)
    _error = field_validator("error")(_validate_error_code)

    @field_validator("answers")
    @classmethod
    def unique_answers(cls, value: list[QuestionAnswer]) -> list[QuestionAnswer]:
        ids = [answer.id for answer in value]
        if len(ids) != len(set(ids)):
            raise ValueError("answers must have unique question ids")
        return value

    @model_validator(mode="after")
    def known_questions(self) -> GateDecision:
        expected = (
            GATE_A_QUESTION_IDS | LEGACY_GATE_A_IDS
            if self.gate == GateId.gate_a
            else GATE_B_QUESTION_IDS
        )
        unknown = {answer.id for answer in self.answers} - expected
        if unknown:
            raise ValueError(f"unknown question ids: {sorted(unknown)}")
        return self


class RequirementCoverage(FrozenModel):
    requirement_id: str
    status: Literal["addressed", "partial", "missed"]
    note: str

    _id = field_validator("requirement_id")(_validate_id)


class ReviewVerdict(FrozenModel):
    case_ref: str | None = None
    case_id: str | None = None
    case_digest: str
    head_digest: str
    packet_digest: str
    verdict: Literal["accept", "changes_required", "human_decision"]
    requirement_coverage: list[RequirementCoverage] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    unresolved_human_decisions: list[str] = Field(default_factory=list)
    model: str
    effort: str
    harness: HarnessId
    usage: UsageCost | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    error: str | None = None
    fixture_provenance: str | None = None

    _case = field_validator("case_digest")(_validate_hash)
    _head = field_validator("head_digest")(_validate_hash)
    _packet = field_validator("packet_digest")(_validate_hash)
    _error = field_validator("error")(_validate_error_code)

    @field_validator("case_ref")
    @classmethod
    def alias(cls, value: str | None) -> str | None:
        if value is not None and not ALIAS_RE.fullmatch(value):
            raise ValueError("case_ref must be a 12-hex alias")
        return value

    @field_validator("case_id")
    @classmethod
    def verdict_case_id(cls, value: str | None) -> str | None:
        return _validate_id(value) if value is not None else None

    @model_validator(mode="after")
    def identify_case(self) -> ReviewVerdict:
        if not self.case_ref and not self.case_id:
            raise ValueError("a verdict needs case_ref or case_id")
        if self.case_ref and self.case_ref != self.case_digest[:12]:
            raise ValueError("case_ref must be derived from case_digest")
        coverage_ids = [item.requirement_id for item in self.requirement_coverage]
        if len(coverage_ids) != len(set(coverage_ids)):
            raise ValueError("requirement coverage ids must be unique")
        finding_ids = [item.id for item in self.findings]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("finding ids must be unique")
        return self


class EscalationDecision(FrozenModel):
    gate: GateId
    case_digest: str
    verdict_digest: str | None = None
    route: Route
    answers: list[QuestionAnswer] = Field(default_factory=list)
    policy_version: str
    rationale: str
    hard_rule: str | None = None
    error: str | None = None

    _case = field_validator("case_digest")(_validate_hash)
    _verdict = field_validator("verdict_digest")(_validate_hash)
    _error = field_validator("error")(_validate_error_code)

    @field_validator("hard_rule")
    @classmethod
    def stable_hard_rule(cls, value: str | None) -> str | None:
        if (
            value is not None
            and value != "security_boundary_floor"
            and not value.startswith("hard_")
        ):
            raise ValueError("hard_rule must be a stable hard-rule code")
        return value

    @model_validator(mode="after")
    def known_questions(self) -> EscalationDecision:
        unknown = {answer.id for answer in self.answers} - GATE_B_QUESTION_IDS
        if unknown:
            raise ValueError(f"unknown question ids: {sorted(unknown)}")
        return self


class StageRecord(FrozenModel):
    name: str
    started_at: str
    ended_at: str
    duration_ms: int = Field(ge=0)
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("started_at", "ended_at")
    @classmethod
    def iso_timestamp(cls, value: str) -> str:
        try:
            datetime.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("stage timestamps must be ISO-8601") from exc
        return value


class RunRecord(FrozenModel):
    run_id: str
    case_ref: str | None = None
    case_id: str | None = None
    linked_case_id: str | None = None
    case_digest: str
    architecture: str
    stages: list[StageRecord] = Field(default_factory=list)
    route: Route
    terminal: Terminal
    escalated: bool
    sol_invoked: bool
    jev_calls: int = Field(ge=0)
    remediation_loops: int = Field(ge=0)
    config_digest: str
    prompt_digests: dict[str, str] = Field(default_factory=dict)
    model_ids: list[str] = Field(default_factory=list)
    invocations: list[InvocationRecord] = Field(default_factory=list)
    backend: Literal["mock", "live"]
    usage: list[UsageCost] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)
    error: str | None = None
    decision_digest: str | None = None
    observation_digest: str | None = None
    invocation_digest: str | None = None

    _case = field_validator("case_digest")(_validate_hash)
    _config = field_validator("config_digest")(_validate_hash)
    _decision = field_validator("decision_digest")(_validate_hash)
    _observation = field_validator("observation_digest")(_validate_hash)
    _invocation = field_validator("invocation_digest")(_validate_hash)
    _error = field_validator("error")(_validate_error_code)

    @field_validator("architecture")
    @classmethod
    def known_architecture(cls, value: str) -> str:
        if value not in {"A0", "A1", "A2", "A3", "A4", "A5", "dual"}:
            raise ValueError("unknown architecture")
        return value

    @field_validator("case_id")
    @classmethod
    def optional_case_id(cls, value: str | None) -> str | None:
        return _validate_id(value) if value is not None else None

    @field_validator("linked_case_id")
    @classmethod
    def optional_linked_case_id(cls, value: str | None) -> str | None:
        return _validate_id(value) if value is not None else None

    @field_validator("model_ids")
    @classmethod
    def unique_models(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("model_ids must be unique")
        return value

    @field_validator("case_ref")
    @classmethod
    def run_alias(cls, value: str | None) -> str | None:
        if value is not None and not ALIAS_RE.fullmatch(value):
            raise ValueError("case_ref must be a 12-hex alias")
        return value

    @model_validator(mode="after")
    def identify_run_case(self) -> RunRecord:
        if not self.case_ref and not self.case_id:
            raise ValueError("a run record needs case_ref or case_id")
        if self.case_ref and self.case_ref != self.case_digest[:12]:
            raise ValueError("case_ref must be derived from case_digest")
        return self


class MatchSpec(FrozenModel):
    requirement_any: list[str] | None = None
    keywords_any: list[str] | None = None
    location_contains: str | None = None
    defect_class_exact: bool = True

    @model_validator(mode="after")
    def has_anchor(self) -> MatchSpec:
        if not (self.requirement_any or self.keywords_any or self.location_contains):
            raise ValueError("match needs a requirement, keyword, or location anchor")
        if self.keywords_any and any(not word.strip() for word in self.keywords_any):
            raise ValueError("match keywords must not be empty")
        if self.requirement_any and len(self.requirement_any) != len(set(self.requirement_any)):
            raise ValueError("match requirement_any must be unique")
        if self.keywords_any and len(self.keywords_any) != len(set(self.keywords_any)):
            raise ValueError("match keywords_any must be unique")
        for requirement in self.requirement_any or []:
            _validate_id(requirement)
        return self


class ExpectedFinding(FrozenModel):
    severity: Severity
    defect_class: DefectClass
    requirement_refs: list[str] = Field(default_factory=list)
    match: MatchSpec

    @field_validator("requirement_refs")
    @classmethod
    def unique_expected_refs(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("expected requirement_refs must be unique")
        for reference in value:
            _validate_id(reference)
        return value


class QuestionLabel(FrozenModel):
    truth: bool


class GoldCase(FrozenModel):
    case_id: str
    expected_findings: list[ExpectedFinding] = Field(default_factory=list)
    question_labels: dict[GateId, dict[str, QuestionLabel]] = Field(default_factory=dict)
    human_required: bool
    verdict_expectation: Literal["accept", "changes_required"]
    labeled_by: Literal["operator", "machine"]
    notes: str = ""

    _id = field_validator("case_id")(_validate_id)

    @model_validator(mode="after")
    def known_question_labels(self) -> GoldCase:
        for gate, labels in self.question_labels.items():
            unknown = set(labels) - CANONICAL_QUESTION_IDS[gate.value]
            if unknown:
                raise ValueError(f"unknown question labels: {sorted(unknown)}")
        return self


class ReviewCase(FrozenModel):
    """Full case metadata used by the engine.

    The packet builder creates a separate projection.  Fields such as
    ``failure_class`` and ``provenance`` are intentionally never copied into
    that projection.
    """

    id: str
    case_ref: str | None = None
    title: str = "Change under review"
    failure_class: DefectClass = DefectClass.other
    description: str = ""
    requirements: list[Requirement] = Field(default_factory=list)
    base_ref: str = "repo"
    patch_ref: str = "change.patch"
    requirements_ref: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    author_lane: Literal["codex", "droid", "human"] = "human"
    provenance: Literal["synthetic_reconstructed", "public_source", "private_replay"] = (
        "synthetic_reconstructed"
    )
    sanitization_note: str = ""
    contracts_ref: str = "contracts.md"
    prior_review_ref: str | None = None
    risk: Literal["low", "medium", "high"] = "medium"
    workstream_subject: str | None = None
    security_boundary_patterns: list[str] = Field(default_factory=list)
    operator_gated: bool = False
    destructive: bool = False
    unresolved_policy: bool = False
    unresolved_adr: bool = False
    case_manifest: list[CaseManifestEntry] = Field(default_factory=list)
    head_digest: str | None = None
    expected_head_digest: str | None = None
    linked_case_id: str | None = None
    # Runtime-only source location.  Digest functions explicitly exclude it.
    case_dir: str | None = None

    _id = field_validator("id")(_validate_id)
    _head = field_validator("head_digest")(_validate_hash)
    _expected_head = field_validator("expected_head_digest")(_validate_hash)

    @field_validator("case_ref")
    @classmethod
    def case_alias(cls, value: str | None) -> str | None:
        if value is not None and not ALIAS_RE.fullmatch(value):
            raise ValueError("case_ref must be a 12-hex alias")
        return value

    @model_validator(mode="after")
    def unique_requirements(self) -> ReviewCase:
        ids = [item.id for item in self.requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("requirement ids must be unique")
        paths = [item.relative_path for item in self.case_manifest]
        if len(paths) != len(set(paths)):
            raise ValueError("case manifest paths must be unique")
        return self


class InvocationRecord(FrozenModel):
    case_digest: str
    head_digest: str
    packet_digest: str
    prompt_digest: str
    config_digest: str
    backend: Literal["mock", "live"]
    model: str
    fixture_version: str
    invocation_digest: str | None = None

    _case = field_validator("case_digest")(_validate_hash)
    _head = field_validator("head_digest")(_validate_hash)
    _packet = field_validator("packet_digest")(_validate_hash)
    _prompt = field_validator("prompt_digest")(_validate_hash)
    _config = field_validator("config_digest")(_validate_hash)
    _invocation = field_validator("invocation_digest")(_validate_hash)


class PacketManifest(FrozenModel):
    files: dict[str, str]
    packet_digest: str
    prompt_template_digest: str

    _packet = field_validator("packet_digest")(_validate_hash)
    _prompt = field_validator("prompt_template_digest")(_validate_hash)

    @field_validator("files")
    @classmethod
    def manifest_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        for relative, digest in value.items():
            normalized = relative.replace("\\", "/")
            if normalized.startswith("/") or ".." in normalized.split("/"):
                raise ValueError("packet manifest paths must be relative")
            _validate_hash(digest)
        return dict(sorted(value.items()))


class PricingEntry(FrozenModel):
    provider: str
    model: str
    input_usd_per_token: str
    output_usd_per_token: str
    effective_date: str
    source: str

    _input_money = field_validator("input_usd_per_token")(_validate_money)
    _output_money = field_validator("output_usd_per_token")(_validate_money)

    @field_validator("effective_date")
    @classmethod
    def iso_effective_date(cls, value: str) -> str:
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("effective_date must be ISO-8601") from exc
        return value


class PricingConfig(FrozenModel):
    entries: list[PricingEntry]

    @model_validator(mode="after")
    def unique_prices(self) -> PricingConfig:
        keys = [(entry.provider, entry.model, entry.effective_date) for entry in self.entries]
        if len(keys) != len(set(keys)):
            raise ValueError("pricing entries must be unique")
        return self


class Step(FrozenModel):
    kind: Literal[
        "deterministic_gates",
        "jev_gate",
        "reviewer",
        "policy_escalation",
        "human",
        "remediate",
    ]
    params: dict[str, Any] = Field(default_factory=dict)

    ALLOWED_KEYS: ClassVar[dict[str, set[str]]] = {
        "deterministic_gates": set(),
        "jev_gate": {"gate"},
        "reviewer": {"conditional", "lane", "component"},
        "policy_escalation": {"gate"},
        "human": set(),
        "remediate": set(),
    }

    @model_validator(mode="after")
    def known_params(self) -> Step:
        unknown = set(self.params) - self.ALLOWED_KEYS[self.kind]
        if unknown:
            raise ValueError(f"unknown step parameters: {sorted(unknown)}")
        if self.kind == "jev_gate" and self.params.get("gate") not in {"gate_a", "gate_b"}:
            raise ValueError("jev_gate requires gate_a or gate_b")
        if self.kind == "policy_escalation" and self.params.get("gate") != "gate_b":
            raise ValueError("policy_escalation requires gate_b")
        return self


class ArchitectureConfig(FrozenModel):
    id: str
    name: str
    steps: list[Step]

    @field_validator("id")
    @classmethod
    def architecture_id(cls, value: str) -> str:
        if value not in {"A0", "A1", "A2", "A3", "A4", "A5", "dual"}:
            raise ValueError("unknown architecture")
        return value


class MetricDefinition(FrozenModel):
    id: str
    population: str
    numerator: str
    denominator: str
    source: str
    missing_data_rule: str
    interpretation: str

    @property
    def missing_rule(self) -> str:
        return self.missing_data_rule


class Scenario(FrozenModel):
    monthly_volume: int = Field(ge=0)
    high_risk_share: str
    human_minutes: str
    human_hourly_rate: str
    reviewer_concurrency: int = Field(gt=0)

    _high = field_validator("high_risk_share")(_validate_money)
    _minutes = field_validator("human_minutes")(_validate_money)
    _rate = field_validator("human_hourly_rate")(_validate_money)

    @field_validator("high_risk_share")
    @classmethod
    def bounded_risk_mix(cls, value: str) -> str:
        if float(value) > 1:
            raise ValueError("high_risk_share must be between zero and one")
        return value


# Forward declarations are not necessary for the current models, but keeping this
# alias public makes callers able to type generic serialized stage payloads.
TypedError = str
