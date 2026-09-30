# Experiment design

## Protocol

Each row is one case, one applied head, and one architecture. A defective head
and its linked fixed head are separate rows with distinct digests. A fixed head
is a replay artifact, not a retroactive mutation of the defective row.

The train/holdout split is a frozen workflow rehearsal. It is useful for
checking that commands and manifests are complete, but this small reconstructed
corpus does not support out-of-sample quality claims. Reviewer packets are
projected before gold is loaded. Expected findings, labels, provenance and
sanitization metadata never enter a packet.

Question sets and policy thresholds are frozen inputs. Thresholds are owned by
policy and never embedded in question text. Sensitivity sweeps use distinct
fixture probability breakpoints plus endpoints, not an arbitrary probability
grid. Hidden outcomes are available only to scoring and calibration after a
run.

All case, head, packet, prompt, configuration, invocation, decision, and
observation identifiers are digest-bound. The runner computes the invocation
record before calling a fixture or provider. Echoed identifiers are checked but
never authoritative. Digests provide integrity and deduplication, not
tamper-proofness.

## State transitions

| Condition | Transition | Terminal |
|---|---|---|
| deterministic `fail` | reject without reviewer | `det_rejected` |
| Gate A below threshold | accept without Sol; do not call Gate B | `accept_no_sol` |
| Sol accepts | complete semantic review | `sol_complete_accept` |
| Sol requests changes | complete semantic review | `sol_complete_changes_required` |
| Gate B below human threshold | record simulated remediation route | `routed_remediate_simulated` |
| Gate B or hard authority floor | route to human | `routed_human` |
| provider, packet, or input error | fail toward review | `error_terminal` |

Ordered hard-rule precedence is: invalid evidence/error, operator-gated or
destructive/irreversible work, unresolved policy/product/ADR decision,
reviewer blocker or material uncertainty, then advisory routing. A security
boundary is a deterministic mandatory-review floor; it is not automatically a
human decision. All remediation language is simulated:
`would_route_to_remediation`.

## Arms

The architecture files under `configs/architectures/` are the machine-readable
matrix. A5 swaps the reviewer slot according to author lane, but that wiring is
simulated. The dual arm invokes a second reviewer only for high-risk rows and
tags its usage with `component=dual_review`.

## Deferred work

Cross-case Jev batching is out of scope for v1. The v1 contract is one
case/head/gate per call. A future batch mode must preserve per-case invocation
records, answer validation, and independent packet digests.

The next live step is shadow-mode collection with a pinned CLI, measured usage,
operator labels, and artifact-backed adjudication. It must not be presented as
an outcome of the mock protocol.
