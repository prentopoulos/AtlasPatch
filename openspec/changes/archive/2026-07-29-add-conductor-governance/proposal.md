## Why

Phase 1 delivered the deterministic operational core with typed, metadata-only telemetry, but its governance guarantees are still asserted in a DRAFT card rather than enforced in code. This phase turns those assertions into by-construction guardrails — the phase-1 typed records are the seam, so each guardrail is an additive filter or gate in front of work that is already metadata-only, not a retrofit. Landing them now (Run B in design D17) closes the "metadata-only ≠ identifier-free" gap and makes the safety boundary CI-provable before the GUI (phase 3) renders over the same records and before distribution (phase 4) sends them off-box.

## What Changes

- **PHI-free write-gate on telemetry (D12).** A deterministic write-time filter wraps the existing `TelemetrySink`: slide stems are pseudonymized before persistence, and any record whose fields match a HIPAA Safe-Harbor identifier pattern (MRN, accession, SSN, dates-of-birth, etc.) is rejected. Additive — the sink already accepts only typed metadata records, so this is a decorator, not a schema change.
- **No-PHI / no-pixel egress assertion.** A CI proof that the layer's only outbound surfaces are CLI argv and on-disk HDF5: no telemetry field can carry a pixel/array (already true by type), and no unexpected external host is contacted during a run. This is the necessary condition the phase-4 BigQuery backend must satisfy.
- **HITL gate on irreversible/expensive recovery actions (D13).** `force_reprocess`, `block_job`, and `quarantine_item` are held for human confirmation; bounded, non-destructive actions (`retry_as_is`, bounded `retry_with_mutation`, `mark_dependents_blocked`, validation, skip) stay autonomous. An explicit `unattended` run waives confirmation but still records the authorizing configuration. `JobConfig.unattended` already exists as the seam.
- **Tamper-evident audit trail.** An append-only, hash-chained record of every consequential action — dispatched actions, recovery decisions, HITL confirmations/waivers, and telemetry-gate rejections — sufficient to reconstruct after a run who or what authorized each irreversible or expensive action, and to detect any post-hoc edit.
- **The System/Model Card, promoted from DRAFT to maintained.** The phase-1 `MODEL_CARD.md` stub is finalized against the shipped code (placeholders filled, non-SaMD boundary and PHI safeguards documented as verifiable technical conditions — not a legal HIPAA certification), and a CI check keeps it from drifting (no unfilled `(to confirm)` placeholders). Phase 7's compliance dossier builds on it.

All of this honors the standing constraints: `atlas_patch/` internals untouched, telemetry stays metadata-only and PHI-free, validation stays operational-not-clinical, and any heavy dependency stays behind the `atlas-patch[orchestrator]` extra (the gates need no new runtime deps).

## Capabilities

### New Capabilities
- `phi-safe-telemetry`: The PHI-free write-gate (pseudonymized slide stems + HIPAA Safe-Harbor identifier rejection at write time) and the no-PHI/no-pixel egress assertion — everything that guarantees no identifier or pixel leaves the layer.
- `hitl-gate`: Human-in-the-loop confirmation on irreversible or expensive recovery actions, with an explicit unattended-autonomy waiver that is itself recorded.
- `audit-trail`: A tamper-evident, append-only, hash-chained log of consequential actions and authorizations, sufficient to reconstruct and verify the integrity of a run's governance decisions.
- `model-card`: The maintained System/Model Card documenting intended use, the non-SaMD scope boundary, decision limits, HITL policy, and PHI safeguards, kept in sync with the shipped safeguards.

### Modified Capabilities
<!-- None. Each guardrail is an additive gate/filter layered in front of the phase-1
     capabilities; the existing run-telemetry and failure-recovery requirements are
     unchanged (the sink still accepts only typed records; recovery still proposes the
     same bounded action set). The new gates sit between them. -->

## Impact

- **New modules** in `atlas_conductor/` (no edits to `atlas_patch/`): a telemetry write-gate that decorates `TelemetrySink`, a pseudonymizer + Safe-Harbor matcher, an HITL confirmation gate consulted by the scheduler before applying an irreversible recovery action, and a hash-chained audit-log writer. All are pure/deterministic and need no new runtime dependency.
- **Wiring**: the scheduler consults the HITL gate before the planner applies `force_reprocess` / `block_job` / `quarantine_item`; the run façade wraps the configured sink in the PHI gate; consequential actions are appended to the audit trail alongside existing telemetry.
- **Config**: reuses the existing `JobConfig.unattended` flag for the HITL waiver.
- **CI (`app` job)**: new tests proving Safe-Harbor rejection (inject a PHI-laden stem via the fake adapter → assert rejection), egress containment (no unexpected host), HITL hold vs. waiver, audit-chain tamper detection, and the Model Card no-placeholder check.
- **Docs**: `MODEL_CARD.md` moves from the archived change into the repo as a maintained artifact and is finalized.
