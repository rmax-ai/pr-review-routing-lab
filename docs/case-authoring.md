# Case authoring

## Directory contract

A public case directory contains:

```text
case.yaml
change.patch
repo/
head/
fixtures/
```

Optional `requirements.yaml`, `contracts.md`, and `prior_review.yaml` are
referenced by `case.yaml`. The case metadata names its author lane, risk,
requirements, workstream subject, and independent `expected_head_digest`.

The loader walks every file under `repo/` and `head/`, plus the named top-level
files, and records `{relative_path, sha256, role}` in sorted order. It verifies
that `change.patch` applies to `repo/`, that all references exist, and that the
computed `head/` file-set digest equals `expected_head_digest`. Any missing,
symlinked, or mismatched input is rejected before routing.

## Requirements and contracts

Write two to four concise requirements. Set `mandatory: true` only when the
requirement is load-bearing. `expects_marker: true` and an optional `surface`
or `marker` create a deterministic review trigger; they do not prove that a
requirement was implemented.

Structured toy contracts should use explicit fields. For example,
completion evidence uses `verified: true` and item `status: open|closed`;
retention evidence declares `max_entries` and `entries`; calibration state
declares `calibration.mode` and `calibration.reset_marker`. The deterministic
analyzer must be able to explain what bytes it inspected.

Gold match specifications need at least one tight anchor:
`requirement_any`, `keywords_any`, or `location_contains`. Prefer a requirement
and a specific location. Keyword lists should be narrow; more than five
keywords or a generic single-word keyword should produce a validation warning.
Expected blockers match produced blockers only. Expected material allows a
material or blocker finding; expected minor allows any severity.

## Provenance and sanitization

Use `synthetic_reconstructed` for reconstructed mechanisms and
`public_source` only after publication review. Include an operator
sanitization note, remove private URLs, absolute home paths, tokens, service
names, and copied private diffs, and verify history before publication.
Fixtures must attest `used_gold: false`. Gold is stored separately and is never
copied into reviewer packets.
