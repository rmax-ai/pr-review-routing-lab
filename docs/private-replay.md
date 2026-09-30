# Private replay overlay

Configure the overlay with the environment variable name
`REVIEW_LAB_PRIVATE_CASES`. Do not put an example absolute path in this
repository. Each overlay child is a normal exact-head case with `repo/`,
`head/`, `change.patch`, `case.yaml`, and local fixtures.

Replay the defective and fixed heads as separate rows. They must have distinct
case and head digests, and a fixed-head row must link back to the defective row.
The loader refuses symlink traversal into or out of an overlay. `--public-only`
refuses to run whenever the variable is set.

When any private provenance is present, the CLI requires `--out` to resolve
outside the checkout and refuses tracked-path output. The report builder refuses
private provenance entirely. Never upload private cases, packets, raw provider
sidecars, or reports. Apply the same sanitization and operator sign-off rules
before any mechanism is reconstructed for public use.
