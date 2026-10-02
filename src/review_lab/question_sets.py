"""Frozen question identifiers shared by configuration, policy, and adapters."""

from __future__ import annotations

CANONICAL_QUESTION_IDS: dict[str, frozenset[str]] = {
    "gate_a": frozenset(
        {
            "needs_semantic_reasoning_beyond_evidence",
            "touches_runtime_state_or_lifecycle",
            "touches_concurrency_or_recovery",
            "touches_authorization_security_or_policy",
            "touches_persistence_schema_or_migration",
            "touches_configuration_or_mode_transitions",
            "requirements_may_be_missing_from_change",
            "evidence_insufficient_to_establish_acceptance",
        }
    ),
    "gate_b": frozenset(
        {
            "requires_new_architecture_product_or_policy_decision",
            "blocker_materially_uncertain",
            "remediation_expands_or_reinterprets_scope",
            "unresolved_requirement_conflict",
            "evidence_insufficient_for_claimed_outcome",
        }
    ),
}

LEGACY_GATE_A_IDS = frozenset(
    {
        "needs_semantic_reasoning",
        "touches_state_lifecycle_concurrency_recovery",
        "touches_auth_security_policy",
        "touches_persistence_schema_migration_config",
        "requirements_may_be_missing",
        "evidence_insufficient",
    }
)

# The first scaffold exposed compact one-question fixtures.  Keep only these
# explicitly registered compatibility keys; arbitrary compact mappings must not
# bypass the full gate contract.
LEGACY_COMPACT_GATE_A_IDS = frozenset(LEGACY_GATE_A_IDS | {"risk"})
