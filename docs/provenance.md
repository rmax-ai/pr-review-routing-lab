# Provenance and publication template

Use this statement for each public case and generated report:

> This artifact is a synthetic reconstruction of a failure mechanism. It
> contains no private repository content, private URLs, credentials, service
> names, session identifiers, or copied private diffs. The artifact was
> reviewed for sanitization before publication.

## Per-file provenance schema

```yaml
relative_path: repo/evidence/state.yaml
role: base|target|case_meta|patch|requirement|contract|prior_review
source_class: synthetic_reconstructed|public_source|private_replay
sha256: lowercase-64-hex
operator_reviewed: true
sanitization_note: "Mechanism only; no source content copied"
```

Generated fixture observations additionally carry:

```yaml
fixture_source: simulated|recorded_live
label_source: operator|machine
adjudicator: none|operator|artifact:<digest>
computation: deterministic
```

Mock observations are mechanics demonstrations. They must not be described as
measured, independent, autonomous, calibrated, or cost-saving outcomes.

## Operator sign-off

- [ ] All files and fixture strings were scanned for private markers.
- [ ] Absolute home paths, secret-like values, private URLs, service names, and
  session identifiers are absent.
- [ ] Case/head/packet manifests and expected digests were recomputed.
- [ ] Git history was checked before publication.
- [ ] The example report says “Mock protocol demonstration” and contains the
  no-claims section.

Operator: ____________________  Date: ____________________
