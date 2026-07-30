## Why

The governance guardrails (phase 2) and the maintained System/Model Card already state the
orchestrator's safeguards as *verifiable technical conditions*, but they are scattered across
the card, the audit trail, and per-capability CI proofs — there is no single artifact that maps
those safeguards onto the obligations an assessor actually asks about (EU AI Act technical
documentation, ISO/IEC 42001 AI-management-system clauses). This phase assembles that dossier
**on top of what already ships** — every claim points at an implemented control and its CI proof —
and adds a run-scoped evidence bundle so a specific run can produce conformity evidence, not just
prose. It is the last planned phase and the natural capstone of the "provable, not asserted" thread
that runs through phases 1–6.

## What Changes

- **A maintained compliance dossier (`COMPLIANCE.md`).** A structured EU AI Act / ISO 42001 dossier
  that (a) records a defensible **risk-tier determination** — the system is operational-only and
  non-SaMD (Model Card §2–§3, D11), so it sits outside high-risk / medical-device scope and the
  obligations that attach are correspondingly limited — and (b) **maps each applicable obligation to
  an implemented control**: EU AI Act Annex IV technical-documentation elements (system description,
  intended purpose, risk management, data governance, human oversight, accuracy/robustness,
  record-keeping/logging) and ISO/IEC 42001 clauses / Annex A controls, each cell citing the module
  and CI test that enforces it (PHI gate, HITL gate, audit chain, determinism, egress guard, card
  drift-check). It stays **honest about scope**: verifiable technical safeguards, explicitly **not** a
  legal conformity attestation, CE marking, or certification.
- **A machine-checkable control register.** The dossier's obligation→control→evidence rows live in a
  structured register (`compliance/controls.yaml`) that CI validates: every cited module path and
  test node exists, no `(to confirm)`-style placeholder remains, and every register row is reflected
  in the rendered dossier. This is the same drift-check discipline as the Model Card's (D24), extended
  to the whole obligation map so the dossier cannot silently rot away from the code.
- **A run-scoped compliance evidence bundle.** An `export-dossier <telemetry-dir>` command (and module)
  assembles, for a completed run, a PHI-free conformity snapshot — audit chain **verified intact** via
  `verify_audit_chain`, HITL holds/approvals/waivers recorded, telemetry-gate rejections, per-slide
  operational outcomes and cohort counts, and the static control register's pass/fail status — sourced
  from the **same audit/telemetry read path** the GUI and `export-report` use (no recompute, PHI-free
  by the same gate). It turns the standing dossier into per-run evidence an assessor can inspect.

All standing constraints hold: `atlas_patch/` internals untouched; the dossier and evidence bundle
read only PHI-free telemetry and the audit trail; validation stays operational-not-clinical; and the
new work needs **no new runtime dependency** (stdlib + the existing telemetry/audit read path; the
register is YAML already available via the toolchain, or JSON with zero deps).

## Capabilities

### New Capabilities
- `compliance-dossier`: The maintained EU AI Act / ISO 42001 dossier — its risk-tier determination,
  its obligation→control→evidence mapping, its honest non-certification scope, and the
  machine-checkable control register plus the CI check that keeps the dossier in sync with the shipped
  controls (no placeholders, every cited module/test exists, register and rendered dossier agree).
- `compliance-evidence`: The run-scoped compliance evidence bundle — an `export-dossier` command that
  assembles a PHI-free per-run conformity snapshot (audit chain verified intact, HITL and gate
  decisions, operational outcomes, control-register status) from the same telemetry/audit read path the
  report export and GUI already use.

### Modified Capabilities
<!-- None. The dossier cross-references the existing model-card and audit-trail capabilities but
     changes none of their requirements: the card stays the system/model card it already is, the audit
     trail's hash-chain contract is unchanged (the evidence bundle only *reads* and verifies it), and
     report-export's read surface is reused as-is. Phase 7 layers a new documentation+evidence
     capability on top; it does not retrofit earlier specs. -->

## Impact

- **New docs (governed artifacts):** `COMPLIANCE.md` at the repo root (matching `MODEL_CARD.md`'s
  placement) and `compliance/controls.yaml` — the structured control register the dossier renders from
  and CI checks.
- **New modules** in `atlas_conductor/` (no edits to `atlas_patch/`): a compliance package that (a)
  loads/validates the control register, (b) renders/checks the dossier against it, and (c) assembles the
  run-scoped evidence bundle from `TelemetryReader` + `verify_audit_chain`. All pure/deterministic and
  read-only over telemetry and the audit trail.
- **CLI (`atlaspatch-conduct`):** a new `export-dossier <telemetry-dir> [--format json|html]` subcommand
  (read-only, mirrors `export-report`).
- **CI (`app` job):** new tests — the control register parses and every cited module/test node resolves;
  the dossier carries no unresolved placeholder and every register row appears in it; the evidence bundle
  is PHI-free (no pixel/array/raw identifier) and reports the audit chain broken when an entry is tampered.
- **Docs / Model Card:** the Model Card §10 "still planned: EU AI Act / ISO 42001 dossier (phase 7)" line
  is updated to "delivered", pointing at `COMPLIANCE.md`; a short usage note for `export-dossier` is added.
