# PR review routing lab

`pr-review-routing-lab` is an offline benchmark engine for studying where a
deterministic check, a semantic reviewer, or a human decision would be placed
in a review workflow. It does not change GitHub, merge branches, run actions,
or perform remediation.

## Research question

For a fixed case and applied head, how do deterministic floors and two advisory
Jev question gates change semantic-review and human-review routing across a
small architecture matrix? The engine measures protocol mechanics, digest
binding, finding matching, arithmetic calibration, and separated cost views.

The repository includes a ten-row reconstructed public corpus, separate gold
labels, and a committed mock example report. The engine can consume public or
private case directories without requiring network access.

## Architecture matrix

| Arm | Chain |
|---|---|
| A0 | deterministic gates → human |
| A1 | deterministic gates → Sol for every gate-passing case → policy |
| A2 | deterministic gates → Gate A → conditional Sol → human |
| A3 | deterministic gates → Sol for every gate-passing case → Gate B → simulated remediation or human |
| A4 | deterministic gates → Gate A → conditional Sol → Gate B → simulated remediation or human |
| A5 | A4 with the reviewer lane swapped by author lane, labeled simulated |
| dual | A4 plus a second reviewer for `risk: high`, with `component=dual_review` usage |

Terminals are explicit: `det_rejected`, `accept_no_sol`,
`sol_complete_accept`, `sol_complete_changes_required`,
`routed_remediate_simulated`, `routed_human`, and `error_terminal`.

## Quickstart

```sh
uv sync
uv run review-lab cases validate cases/public
uv run review-lab experiment run \
  --architectures A0,A1,A2,A3,A4,A5,dual \
  --cases cases/public --split all --backend mock --out runs/example
uv run review-lab report build --run runs/example --gold gold --out reports/example_mock.md
```

The default mock path is offline; decisions and digests are deterministic.
Set `REVIEW_LAB_NOW` when byte-identical fresh traces are required.
`UV_OFFLINE=1 uv sync --frozen` is suitable for an already warmed cache.

Metric rates are aggregated from persisted integer fields named
`<metric_id>_numerator` and `<metric_id>_denominator`, rather than averaging
per-case rates. A zero-denominator row persists `0, 0` and contributes no rate.
Usage and cost metrics keep measured and simulated components separate;
incomplete components publish an explicit partial-usage reason instead of a
fabricated zero. Resume identity includes the full runner configuration,
including model and effort.

## Mock and live boundaries

Mock Jev envelopes and reviewer fixtures are simulated mechanics drivers. They
are labeled `source=simulated` and are never evidence of model quality,
calibration quality, cost savings, autonomy, or reviewer independence.

The live Jev subprocess is opt-in and requires both `--allow-live` and
`REVIEW_LAB_JEV_BIN`. Provider output is schema-validated, bounded, scrubbed
into a local sidecar on failure, and never used as a free-text machine value.
The Codex command shim is also behind an explicit reviewer command. No live
provider is used by tests or the default run path.

## Data and privacy

Case loading verifies a canonical manifest, patch applicability, expected
applied-head digest, and referenced files before routing. Reviewer packets use
a 12-hex opaque case alias and contain no gold or expected-finding fields.
SHA-256 values provide integrity and deduplication only, not tamper-proofness.

Private exact-head replay is configured with the environment variable name
`REVIEW_LAB_PRIVATE_CASES`. See `docs/private-replay.md`; private outputs must
be outside the checkout and are never uploaded. The report builder refuses
private provenance.

## Honesty and limitations

This project demonstrates an evaluation protocol on small structured toy
contracts. The later example report is titled **Mock protocol demonstration**
and is generated from mock backends. It must not be read as a model benchmark,
a calibration study, a savings estimate, an autonomy claim, or an
independence claim. Train/holdout splits are workflow rehearsals, not
out-of-sample evidence. Live shadow-mode collection and operator adjudication
are the next step.

Cross-case Jev batching is deliberately deferred in v1. Remediation and merge
routes are recorded as `would_route_to_remediation`; the lab never executes
them.
