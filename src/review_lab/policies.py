"""Policy-owned thresholds and deterministic routing floors."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .models import DeterministicEvidence, QuestionAnswer, ReviewCase, Route
from .question_sets import CANONICAL_QUESTION_IDS

POLICY_VERSION = "policy-v1"
DEFAULT_THRESHOLDS: dict[str, float] = {
    "gate_a.t_mid": 0.45,
    "gate_a.t_hi": 0.70,
    "gate_b.t_high": 0.70,
}
GATE_A_HARD_IDS = {
    "touches_authorization_security_or_policy",
    "touches_persistence_schema_or_migration",
    "touches_auth_security_policy",
    "touches_persistence_schema_migration_config",
}

# The aliases keep the first draft's public API usable while the frozen question
# ids remain the canonical keys in all generated configs.
GATE_A_IDS = set(CANONICAL_QUESTION_IDS["gate_a"])
GATE_B_IDS = set(CANONICAL_QUESTION_IDS["gate_b"])


@dataclass(frozen=True)
class PolicyResult:
    route: Route
    rationale: str
    hard_rule: str | None = None


def probability(answer: QuestionAnswer) -> float:
    """Return the probability of a positive boolean answer."""

    if "true" in answer.probabilities:
        return float(answer.probabilities["true"])
    if answer.type == "boolean" and isinstance(answer.value, bool):
        return 1.0 if answer.value else 0.0
    if answer.derived_confidence is not None:
        return float(answer.derived_confidence)
    return 0.0


def _statuses(evidence: Iterable[DeterministicEvidence]) -> list[DeterministicEvidence]:
    return list(evidence)


def deterministic_policy(evidence: Iterable[DeterministicEvidence]) -> PolicyResult:
    """Return the deterministic floor before Jev is considered."""

    rows = _statuses(evidence)
    if any(row.status == "fail" for row in rows):
        return PolicyResult(
            Route.deterministic_reject, "deterministic invariant failed", "hard_fail"
        )
    if any(row.status in {"mandatory_review", "inconclusive"} for row in rows):
        return PolicyResult(Route.sol_review, "deterministic review floor", "hard_review_floor")
    return PolicyResult(Route.accept, "deterministic gates passed")


def gate_a_policy(
    answers: Iterable[QuestionAnswer],
    *,
    deterministic_floor: bool = False,
    error: str | None = None,
    threshold: float | None = None,
    hard_threshold: float | None = None,
) -> PolicyResult:
    if error:
        return PolicyResult(
            Route.sol_review, "Gate A error fails toward semantic review", "hard_jev_error"
        )
    if deterministic_floor:
        return PolicyResult(Route.sol_review, "deterministic floor", "hard_review_floor")
    regular_limit = DEFAULT_THRESHOLDS["gate_a.t_hi"] if threshold is None else threshold
    hard_limit = DEFAULT_THRESHOLDS["gate_a.t_mid"] if hard_threshold is None else hard_threshold
    triggered = any(
        probability(answer) >= (hard_limit if answer.id in GATE_A_HARD_IDS else regular_limit)
        for answer in answers
    )
    if triggered:
        return PolicyResult(Route.sol_review, "Gate A question exceeded registered threshold")
    return PolicyResult(Route.accept_no_sol, "Gate A found no semantic-review trigger")


def gate_b_policy(
    answers: Iterable[QuestionAnswer],
    *,
    hard_rule: str | None = None,
    error: str | None = None,
    threshold: float | None = None,
) -> PolicyResult:
    if error:
        return PolicyResult(
            Route.human_review, "Gate B error fails toward human review", "hard_jev_error"
        )
    if hard_rule and hard_rule != "security_boundary_floor":
        return PolicyResult(Route.human_review, "hard rule overrides Jev", hard_rule)
    limit = DEFAULT_THRESHOLDS["gate_b.t_high"] if threshold is None else threshold
    if any(probability(answer) >= limit for answer in answers):
        return PolicyResult(Route.human_review, "Gate B question exceeded human threshold")
    return PolicyResult(Route.remediate_simulated, "would_route_to_remediation")


def hard_rule_for(
    case: ReviewCase | object,
    evidence: Iterable[DeterministicEvidence],
    *,
    reviewer_error: str | None = None,
    reviewer_blocker: bool = False,
) -> str | None:
    """Ordered hard-rule identifiers.

    Security is deliberately returned as a floor that Gate B may not turn into
    an automatic human route by itself.  The other authority and validity rules
    are human floors.
    """

    rows = list(evidence)
    if any(row.status == "fail" for row in rows):
        return "hard_deterministic_failure"
    if reviewer_error or any(row.status == "inconclusive" for row in rows):
        return "hard_invalid_evidence"
    if getattr(case, "operator_gated", False):
        return "hard_operator_gated"
    if getattr(case, "destructive", False):
        return "hard_destructive_irreversible"
    if getattr(case, "unresolved_policy", False) or getattr(case, "unresolved_adr", False):
        return "hard_unresolved_policy"
    if reviewer_blocker:
        return "hard_reviewer_blocker"
    if any(row.gate == "security_boundary" and row.status == "mandatory_review" for row in rows):
        return "security_boundary_floor"
    return None


def validate_question_ids(gate: str, answers: Iterable[QuestionAnswer]) -> None:
    if gate not in {"a", "gate_a", "b", "gate_b"}:
        raise ValueError(f"unknown gate: {gate}")
    expected = GATE_A_IDS if gate in {"a", "gate_a"} else GATE_B_IDS
    unknown = {answer.id for answer in answers} - expected
    if unknown:
        raise ValueError(f"unknown question ids: {sorted(unknown)}")
