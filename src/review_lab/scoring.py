"""Finding-level scoring without any Jev dependency.

Matching is a maximum-weight bipartite problem.  Produced findings are ordered
by severity, descending confidence, and id; expected findings retain their
gold-file order.  Equal-weight solutions use the lexicographically smallest
``(produced_id, expected_index)`` sequence.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .models import Finding, GoldCase, Route, Severity


@dataclass(frozen=True)
class MatchAudit:
    produced_id: str
    expected_index: int
    taxonomy: str
    weight: int


@dataclass(frozen=True)
class Score:
    exact_matches: int
    misses: int
    spurious_blockers: int
    advisory_noise: int
    expected_count: int
    produced_count: int
    requirement_coverage_recall: float
    claimed_addressed_recall: float = 0.0
    severity_exactness_rate: float = 0.0
    taxonomy_counts: Mapping[str, int] = field(default_factory=dict)
    audits: tuple[MatchAudit, ...] = ()
    matched_expected_indices: tuple[int, ...] = ()
    expected_by_severity: Mapping[str, int] = field(default_factory=dict)
    matched_by_severity: Mapping[str, int] = field(default_factory=dict)
    # These flat counts are retained alongside the rates.  Aggregating the
    # rates themselves (for example by taking their mean) gives the wrong
    # answer when cases have different numbers of findings.
    expected_requirement_count: int = 0
    covered_requirement_count: int = 0

    @property
    def recall(self) -> float:
        return self.exact_matches / self.expected_count if self.expected_count else 1.0

    @property
    def blocker_recall(self) -> float:
        return self._recall_for(Severity.blocker)

    @property
    def material_recall_including_blocker(self) -> float:
        return self._recall_for_set({Severity.blocker, Severity.material})

    @property
    def material_recall_only(self) -> float:
        return self._recall_for(Severity.material)

    def _recall_for(self, severity: Severity) -> float:
        return self._recall_for_set({severity})

    def _recall_for_set(self, severities: set[Severity]) -> float:
        expected = sum(self.expected_by_severity.get(item.value, 0) for item in severities)
        matched = sum(self.matched_by_severity.get(item.value, 0) for item in severities)
        return matched / expected if expected else 1.0


def _severity_ok(expected: Severity, produced: Severity) -> bool:
    allowed = {
        Severity.blocker: {Severity.blocker},
        Severity.material: {Severity.material, Severity.blocker},
        Severity.minor: {Severity.minor, Severity.material, Severity.blocker},
    }
    return produced in allowed[expected]


def _candidate_reasons(finding: Finding, expected: Any) -> tuple[bool, int, str]:
    spec = expected.match
    if spec.defect_class_exact and finding.defect_class != expected.defect_class:
        return False, 0, "unsupported"
    if not _severity_ok(expected.severity, finding.severity):
        return False, 0, "wrong_severity"
    if spec.requirement_any and not set(finding.requirement_refs).intersection(
        spec.requirement_any
    ):
        return False, 0, "wrong_requirement"
    haystack = f"{finding.evidence} {finding.location or ''}".casefold()
    if spec.keywords_any and not any(word.casefold() in haystack for word in spec.keywords_any):
        return False, 0, "unsupported"
    if (
        spec.location_contains
        and spec.location_contains.casefold() not in (finding.location or "").casefold()
    ):
        return False, 0, "unsupported"
    weight = 1_000_000
    weight += 10_000 if finding.severity == expected.severity else 0
    weight += int(finding.confidence * 100)
    # Stronger requirement and location anchors make ties deterministic while
    # retaining the same semantics.
    weight += 10 if spec.requirement_any else 0
    weight += 5 if spec.location_contains else 0
    return True, weight, "exact" if finding.severity == expected.severity else "wrong_severity"


def _match(finding: Finding, expected: Any) -> tuple[bool, int]:
    """Compatibility helper exposing the candidate predicate and weight."""

    matched, weight, _ = _candidate_reasons(finding, expected)
    return matched, weight


def _ordered_findings(findings: Iterable[Finding]) -> list[Finding]:
    rank = {Severity.blocker: 0, Severity.material: 1, Severity.minor: 2}
    return sorted(findings, key=lambda item: (rank[item.severity], -item.confidence, item.id))


def _matching(
    produced: list[Finding],
    gold: GoldCase,
) -> tuple[list[tuple[int, int, int, str]], dict[tuple[int, int], tuple[int, str]]]:
    candidates: dict[tuple[int, int], tuple[int, str]] = {}
    for pi, finding in enumerate(produced):
        for ei, expected in enumerate(gold.expected_findings):
            ok, weight, taxonomy = _candidate_reasons(finding, expected)
            if ok:
                candidates[pi, ei] = weight, taxonomy

    if not produced or not gold.expected_findings:
        return [], candidates
    row_count = len(produced)
    expected_count = len(gold.expected_findings)
    column_count = max(row_count, expected_count)
    # Positive candidate weights make zero-filled dummy/non-candidate cells the
    # explicit unmatched option.  The small deterministic bonus only breaks
    # equal-weight ties; it cannot outweigh one unit of match weight.
    tie_scale = row_count * (row_count * (expected_count + 1) + expected_count) + 1
    scores = [[0] * column_count for _ in range(row_count)]
    for (pi, ei), (weight, _) in candidates.items():
        bonus = (row_count - pi) * (expected_count + 1) + (expected_count - ei)
        scores[pi][ei] = weight * tie_scale + bonus
    max_score = max(max(row) for row in scores)
    costs = [[max_score - score for score in row] for row in scores]

    # Hungarian assignment for a rectangular matrix with row_count <=
    # column_count.  Dummy columns are present when produced findings outnumber
    # expected findings, and zero/non-candidate cells remain unmatched.
    u = [0] * (row_count + 1)
    v = [0] * (column_count + 1)
    parent = [0] * (column_count + 1)
    way = [0] * (column_count + 1)
    for row in range(1, row_count + 1):
        parent[0] = row
        column = 0
        minimum = [None] + [None] * column_count
        used = [False] * (column_count + 1)
        while True:
            used[column] = True
            current_row = parent[column]
            delta = None
            next_column = 0
            for candidate_column in range(1, column_count + 1):
                if used[candidate_column]:
                    continue
                current = (
                    costs[current_row - 1][candidate_column - 1]
                    - u[current_row]
                    - v[candidate_column]
                )
                if minimum[candidate_column] is None or current < minimum[candidate_column]:
                    minimum[candidate_column] = current
                    way[candidate_column] = column
                if delta is None or minimum[candidate_column] < delta:
                    delta = minimum[candidate_column]
                    next_column = candidate_column
            for candidate_column in range(column_count + 1):
                if used[candidate_column]:
                    u[parent[candidate_column]] += delta or 0
                    v[candidate_column] -= delta or 0
                elif candidate_column:
                    minimum[candidate_column] = (
                        minimum[candidate_column] - delta
                        if minimum[candidate_column] is not None
                        else None
                    )
            column = next_column
            if parent[column] == 0:
                break
        while True:
            previous = way[column]
            parent[column] = parent[previous]
            column = previous
            if column == 0:
                break

    assigned: dict[int, int] = {
        parent[column] - 1: column - 1
        for column in range(1, column_count + 1)
        if parent[column] and parent[column] <= row_count
    }
    pairs = tuple(
        (pi, ei)
        for pi, ei in sorted(assigned.items())
        if ei < expected_count and (pi, ei) in candidates
    )
    rows = [
        (weight, pi, ei, taxonomy)
        for (pi, ei), (weight, taxonomy) in candidates.items()
        if (pi, ei) in pairs
    ]
    return sorted(rows, key=lambda row: (row[1], row[2])), candidates


def _coverage_from_findings(
    findings: list[Finding],
    gold: GoldCase,
    matches: list[tuple[int, int, int, str]],
) -> tuple[float, set[str]]:
    targets = {ref for expected in gold.expected_findings for ref in expected.requirement_refs}
    covered: set[str] = set()
    for _, pi, ei, _ in matches:
        expected_refs = set(gold.expected_findings[ei].requirement_refs)
        covered.update(expected_refs.intersection(findings[pi].requirement_refs))
    return (len(covered) / len(targets) if targets else 1.0), covered


def score_findings(findings: Iterable[Finding], gold: GoldCase) -> Score:
    produced = _ordered_findings(findings)
    matches, candidates = _matching(produced, gold)
    matched_produced = {row[1] for row in matches}
    matched_expected = {row[2] for row in matches}
    audits = tuple(
        MatchAudit(produced[pi].id, ei, taxonomy, weight) for weight, pi, ei, taxonomy in matches
    )
    taxonomy_counts = Counter(audit.taxonomy for audit in audits)
    for pi, finding in enumerate(produced):
        if pi in matched_produced:
            continue
        available = [
            reason for (candidate_pi, _), (_, reason) in candidates.items() if candidate_pi == pi
        ]
        if available:
            taxonomy_counts["duplicate"] += 1
        elif any(
            finding.defect_class == expected.defect_class for expected in gold.expected_findings
        ):
            # A same-class, non-candidate finding is most often a severity or
            # requirement mismatch.  Keep the taxonomy explicit.
            reasons = [
                _candidate_reasons(finding, expected)[2] for expected in gold.expected_findings
            ]
            taxonomy_counts[
                next(
                    (
                        reason
                        for reason in ("wrong_severity", "wrong_requirement")
                        if reason in reasons
                    ),
                    "unsupported",
                )
            ] += 1
        else:
            taxonomy_counts["unsupported"] += 1
    coverage, _ = _coverage_from_findings(produced, gold, matches)
    exact = sum(1 for _, _, _, taxonomy in matches if taxonomy == "exact")
    exactness = exact / len(matches) if matches else (1.0 if not produced else 0.0)
    expected_by_severity = Counter(expected.severity.value for expected in gold.expected_findings)
    matched_by_severity = Counter(
        gold.expected_findings[ei].severity.value for _, _, ei, _ in matches
    )
    targets = {
        ref for expected in gold.expected_findings for ref in expected.requirement_refs
    }
    return Score(
        exact_matches=len(matches),
        misses=len(gold.expected_findings) - len(matched_expected),
        spurious_blockers=sum(
            finding.severity == Severity.blocker
            for index, finding in enumerate(produced)
            if index not in matched_produced
        ),
        advisory_noise=sum(
            finding.severity != Severity.blocker
            for index, finding in enumerate(produced)
            if index not in matched_produced
        ),
        expected_count=len(gold.expected_findings),
        produced_count=len(produced),
        requirement_coverage_recall=coverage,
        severity_exactness_rate=exactness,
        taxonomy_counts=dict(sorted(taxonomy_counts.items())),
        audits=audits,
        matched_expected_indices=tuple(sorted(matched_expected)),
        expected_by_severity=dict(sorted(expected_by_severity.items())),
        matched_by_severity=dict(sorted(matched_by_severity.items())),
        expected_requirement_count=len(targets),
        covered_requirement_count=len(_coverage_from_findings(produced, gold, matches)[1]),
    )


def score_verdict(verdict: Any, gold: GoldCase) -> Score:
    score = score_findings(verdict.findings, gold)
    targets = {ref for expected in gold.expected_findings for ref in expected.requirement_refs}
    claimed = {
        item.requirement_id for item in verdict.requirement_coverage if item.status == "addressed"
    }
    claimed_recall = len(targets.intersection(claimed)) / len(targets) if targets else 1.0
    findings_by_id = {finding.id: finding for finding in verdict.findings}
    covered = set(targets).intersection(claimed)
    for audit in score.audits:
        finding = findings_by_id.get(audit.produced_id)
        if finding is None:
            continue
        expected_refs = set(gold.expected_findings[audit.expected_index].requirement_refs)
        covered.update(expected_refs.intersection(finding.requirement_refs))
    finding_coverage = len(covered) / len(targets) if targets else 1.0
    return Score(
        **{
            **score.__dict__,
            "requirement_coverage_recall": finding_coverage,
            "claimed_addressed_recall": claimed_recall,
            "covered_requirement_count": len(covered),
        }
    )


def validate_adjudication_artifact(
    artifact: Mapping[str, Any],
    jev_invocation_digests: Iterable[str],
) -> None:
    digest = artifact.get("invocation_digest") or artifact.get("digest")
    if digest in set(jev_invocation_digests):
        raise ValueError("adjudication digest must not equal a Jev invocation digest")


def required_but_unmentioned(
    gold: GoldCase,
    findings: Iterable[Finding],
    requirements: Iterable[Any] | None = None,
) -> int:
    if requirements is None:
        required = {
            reference
            for expected in gold.expected_findings
            for reference in expected.requirement_refs
        }
    else:
        required = {
            requirement.get("id", "") if isinstance(requirement, dict) else requirement.id
            for requirement in requirements
            if (
                requirement.get("mandatory", False)
                if isinstance(requirement, dict)
                else getattr(requirement, "mandatory", False)
            )
        }
    mentioned = {reference for finding in findings for reference in finding.requirement_refs}
    return len(required - mentioned)


def score_metrics(score: Score) -> dict[str, float | int | None]:
    expected_blockers = score.expected_by_severity.get(Severity.blocker.value, 0)
    expected_material = score.expected_by_severity.get(Severity.material.value, 0)
    matched_blockers = score.matched_by_severity.get(Severity.blocker.value, 0)
    matched_material = score.matched_by_severity.get(Severity.material.value, 0)
    matched_material_and_blocker = matched_blockers + matched_material
    matched_findings = len(score.audits)
    produced = score.produced_count
    exact = sum(audit.taxonomy == "exact" for audit in score.audits)
    def rate(numerator: int, denominator: int) -> float | None:
        return numerator / denominator if denominator else None

    # Keep the old rate keys for callers, but also publish the numerator and
    # denominator as flat fields.  The report builder can then sum counts
    # across rows instead of averaging per-row rates.
    return {
        "blocker_recall": rate(matched_blockers, expected_blockers),
        "blocker_recall_numerator": matched_blockers,
        "blocker_recall_denominator": expected_blockers,
        "material_recall_including_blocker": rate(
            matched_material_and_blocker, expected_blockers + expected_material
        ),
        "material_recall_including_blocker_numerator": matched_material_and_blocker,
        "material_recall_including_blocker_denominator": expected_blockers + expected_material,
        "material_recall_only": rate(matched_material, expected_material),
        "material_recall_only_numerator": matched_material,
        "material_recall_only_denominator": expected_material,
        "requirement_coverage_recall": rate(
            score.covered_requirement_count, score.expected_requirement_count
        ),
        "requirement_coverage_recall_numerator": score.covered_requirement_count,
        "requirement_coverage_recall_denominator": score.expected_requirement_count,
        "claimed_addressed_recall": score.claimed_addressed_recall,
        "spurious_blocker_rate": (
            score.spurious_blockers / produced if produced else None
        ),
        "spurious_blocker_rate_numerator": score.spurious_blockers,
        "spurious_blocker_rate_denominator": produced,
        "severity_exactness_rate": rate(exact, matched_findings),
        "severity_exactness_rate_numerator": exact,
        "severity_exactness_rate_denominator": matched_findings,
        "overcall_rate": (
            (score.spurious_blockers + score.advisory_noise) / produced
            if produced
            else None
        ),
        "overcall_rate_numerator": score.spurious_blockers + score.advisory_noise,
        "overcall_rate_denominator": produced,
        "exact_matches": score.exact_matches,
        "misses": score.misses,
    }


def route_metrics(
    records: Iterable[Any],
    gold_by_case: Mapping[str, GoldCase],
) -> list[dict[str, Any]]:
    """Compute safety and avoidance observations with explicit denominators."""

    rows = list(records)
    error_rows = [
        row
        for row in rows
        if getattr(row, "error", None)
        or getattr(getattr(row, "terminal", None), "value", getattr(row, "terminal", None))
        == "error_terminal"
    ]
    rows = [row for row in rows if row not in error_rows]
    no_sol = [row for row in rows if getattr(row, "route", None) == Route.accept_no_sol]
    false_safe = sum(
        bool(
            gold_by_case.get(row.case_id)
            and (
                gold_by_case[row.case_id].human_required
                or any(
                    finding.severity in {Severity.blocker, Severity.material}
                    for finding in gold_by_case[row.case_id].expected_findings
                )
            )
        )
        for row in no_sol
    )
    gate_b_rows = [
        row for row in rows if any(stage.name == "gate_b" for stage in getattr(row, "stages", []))
    ]
    non_human = [row for row in gate_b_rows if getattr(row, "route", None) != Route.human_review]
    false_no_human = sum(
        bool(gold_by_case.get(row.case_id) and gold_by_case[row.case_id].human_required)
        for row in non_human
    )
    eligible = [
        row
        for row in rows
        if getattr(getattr(row, "terminal", None), "value", getattr(row, "terminal", None))
        != "det_rejected"
    ]
    # A loop metric is about the fixed-head replay population, not merely about
    # whichever rows happened to route to remediation.  ``linked_case_id`` is
    # persisted on each record so this calculation remains reproducible when
    # only records.jsonl is available.
    linked_fixed_head_rows = [
        row for row in eligible if getattr(row, "linked_case_id", None) is not None
    ]

    def loop_count(row: Any, *, simulated: bool) -> int:
        artifacts = [
            stage
            for stage in getattr(row, "stages", [])
            if stage.name == "remediation_loop"
        ]
        if not artifacts:
            return 0
        artifact_is_simulated = any(stage.data.get("simulated") is True for stage in artifacts)
        return getattr(row, "remediation_loops", 0) if artifact_is_simulated is simulated else 0

    simulated_loop_count = sum(loop_count(row, simulated=True) for row in linked_fixed_head_rows)
    executed_loop_count = sum(loop_count(row, simulated=False) for row in linked_fixed_head_rows)
    simulated = all(getattr(row, "backend", "mock") == "mock" for row in rows) if rows else False
    fixture_source = "simulated" if simulated else "measured"
    output = [
        {
            "id": "gate_a_false_safe_rate",
            "numerator": false_safe,
            "denominator": len(no_sol),
            "value": false_safe / len(no_sol) if no_sol else None,
            "label_source": "operator",
            "adjudicator": "none",
            "fixture_source": fixture_source,
            "computation": "deterministic",
        },
        {
            "id": "error_rows_skipped",
            "numerator": len(error_rows),
            "denominator": len(error_rows) + len(rows),
            "value": len(error_rows),
            "label_source": "machine",
            "adjudicator": "none",
            "fixture_source": fixture_source,
            "computation": "deterministic",
        },
        {
            "id": "gate_b_false_no_human_rate",
            "numerator": false_no_human,
            "denominator": len(non_human),
            "value": false_no_human / len(non_human) if non_human else None,
            "label_source": "operator",
            "adjudicator": "none",
            "fixture_source": fixture_source,
            "computation": "deterministic",
        },
    ]
    output.extend(
        [
            {
                "id": "sol_avoidance_rate",
                "numerator": sum(not row.sol_invoked for row in eligible),
                "denominator": len(eligible),
                "value": (
                    sum(not row.sol_invoked for row in eligible) / len(eligible)
                    if eligible
                    else None
                ),
                "label_source": "operator",
                "adjudicator": "none",
                "fixture_source": fixture_source,
                "computation": "deterministic",
            },
            {
                "id": "human_avoidance_rate",
                "numerator": sum(row.route != Route.human_review for row in eligible),
                "denominator": len(eligible),
                "value": (
                    sum(row.route != Route.human_review for row in eligible) / len(eligible)
                    if eligible
                    else None
                ),
                "label_source": "operator",
                "adjudicator": "none",
                "fixture_source": fixture_source,
                "computation": "deterministic",
            },
            {
                "id": "remediation_eligibility_rate",
                "numerator": sum(row.route == Route.remediate_simulated for row in eligible),
                "denominator": len(eligible),
                "value": (
                    sum(row.route == Route.remediate_simulated for row in eligible) / len(eligible)
                    if eligible
                    else None
                ),
                "label_source": "operator",
                "adjudicator": "none",
                "fixture_source": fixture_source,
                "computation": "deterministic",
            },
            {
                "id": "review_loops",
                "numerator": executed_loop_count,
                "denominator": len(linked_fixed_head_rows),
                "value": (
                    executed_loop_count / len(linked_fixed_head_rows)
                    if linked_fixed_head_rows
                    else None
                ),
                "label_source": "operator",
                "adjudicator": "none",
                "fixture_source": fixture_source,
                "computation": "deterministic",
            },
            {
                "id": "review_loops_simulated",
                "numerator": simulated_loop_count,
                "denominator": len(linked_fixed_head_rows),
                "value": (
                    simulated_loop_count / len(linked_fixed_head_rows)
                    if linked_fixed_head_rows
                    else None
                ),
                "label_source": "machine",
                "adjudicator": "none",
                "fixture_source": fixture_source,
                "computation": "deterministic",
            },
            {
                "id": "jev_calls_per_pr",
                "numerator": sum(row.jev_calls for row in rows),
                "denominator": len(rows),
                "value": sum(row.jev_calls for row in rows) / len(rows) if rows else None,
                "label_source": "machine",
                "adjudicator": "none",
                "fixture_source": fixture_source,
                "computation": "deterministic",
            },
            {
                "id": "sol_calls_per_pr",
                "numerator": sum(
                    sum(stage.name in {"sol_review", "dual_review"} for stage in row.stages)
                    for row in rows
                ),
                "denominator": len(rows),
                "value": (
                    sum(
                        sum(stage.name in {"sol_review", "dual_review"} for stage in row.stages)
                        for row in rows
                    )
                    / len(rows)
                    if rows
                    else None
                ),
                "label_source": "machine",
                "adjudicator": "none",
                "fixture_source": fixture_source,
                "computation": "deterministic",
            },
        ]
    )
    for metric in output:
        metric["numerator_value"] = (
            metric["numerator"] if isinstance(metric.get("numerator"), (int, float)) else None
        )
        metric["denominator_value"] = (
            metric["denominator"] if isinstance(metric.get("denominator"), (int, float)) else None
        )
    return output
