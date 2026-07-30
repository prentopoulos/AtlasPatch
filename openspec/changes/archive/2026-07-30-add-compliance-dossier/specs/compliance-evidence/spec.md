## ADDED Requirements

### Requirement: A run-scoped compliance evidence bundle can be exported

The conductor SHALL be able to export, for a completed run, a compliance evidence bundle that
assembles the run's conformity evidence: the result of verifying the run's audit chain, the run's
human-in-the-loop decisions (holds, approvals, waivers) and telemetry-gate rejections recorded in the
audit trail, the run's per-slide operational outcomes and cohort counts, and the pass/fail status of
the static control register. The bundle SHALL be exportable in a machine-readable form (JSON) and MAY
also be exportable as a self-contained HTML document with no embedded scripts or images.

#### Scenario: The bundle reports the audit chain verification result

- **WHEN** an evidence bundle is exported for a run whose audit trail is intact
- **THEN** the bundle reports the audit chain as verified intact

#### Scenario: The bundle carries the run's governance decisions and outcomes

- **WHEN** an evidence bundle is exported for a completed run
- **THEN** it contains the run's HITL holds/approvals/waivers and gate rejections, the per-slide
  operational outcomes, and the cohort counts

### Requirement: The evidence bundle is sourced from the shared read path and is PHI-free

The evidence bundle SHALL be assembled from the same telemetry and audit read path the report export
and GUI already use — the audit trail read together with `verify_audit_chain`, and the PHI-free
telemetry reader — not recomputed from a separate path, so the bundle cannot diverge from what the
report and GUI report for the run. The bundle SHALL contain only PHI-free operational metadata:
pseudonymized slide stems, verdicts, reason codes, counts, and governance decisions — and no slide
pixel, mask, embedding, or raw Safe-Harbor identifier.

#### Scenario: Export carries no PHI and no pixels

- **WHEN** an evidence bundle is exported for a run that gated its telemetry
- **THEN** it contains only PHI-free operational metadata and no slide pixel, mask, embedding, or raw
  identifier

#### Scenario: Export and report agree on a run

- **WHEN** the same run is exported as a report sibling and as a compliance evidence bundle
- **THEN** the per-slide verdicts and cohort counts are identical in both

### Requirement: The evidence bundle surfaces a tampered audit chain

Because the bundle verifies the audit chain rather than trusting it, a run whose audit trail has been
edited, reordered, or truncated after the fact SHALL be reported by the bundle as having a broken
chain, identifying that verification failed — so the evidence bundle cannot certify a tampered run as
intact.

#### Scenario: A tampered audit trail is reported as broken

- **WHEN** an entry in a run's audit trail is altered and an evidence bundle is then exported
- **THEN** the bundle reports the audit chain as broken rather than intact
