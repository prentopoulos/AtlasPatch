# Project

AtlasPatch is a computational-pathology preprocessing tool: its CLI segments tissue
(SAM2), extracts patch coordinates, and embeds patch features into one canonical HDF5 per
slide. This repository is a fork that extends AtlasPatch with an **orchestration layer**
(`atlas_conductor`) for running the pipeline reliably at cohort scale — planning,
dispatching, validating, and recovering runs without touching the ML pipeline.

Development follows the phase loop in `WORKFLOW.md`: one phase = one OpenSpec change = one
PR. Use the `next-phase` skill to run a phase.

## Phases

Phases are worked top-to-bottom. "Next unstarted phase" for `/opsx:propose` means the
first one below whose status is not Done.

| # | Phase (change name) | Status | Summary |
|---|---------------------|--------|---------|
| 1 | `add-atlas-conductor` | Done | The operational core: planner / worker / validator / recovery as plain in-process components over the existing CLI + HDF5 — job planning, dispatch, structural validation, rule-based recovery, and metadata-only local telemetry. Built as internal slices A1 (walking skeleton) → A2 (reconciliation intelligence) → A3 (recovery), each green-in-CI. MVP commands: `segment-and-get-coords` and `process`. Deterministic-core invariant (no clinical reasoning) holds here by construction. |
| 2 | `add-conductor-governance` | Done | By-construction guardrails: PHI-free write-gate (pseudonymized stems + HIPAA Safe-Harbor rejection), HITL gate on irreversible/expensive actions, no-PHI/no-pixel egress assertion, tamper-evident audit trail, and the Model Card. Additive — the phase-1 typed telemetry records are the seam, so this is a filter/gate on top, not a retrofit. |
| 3 | `add-conductor-gui` | Done | Read-only observability GUI (Streamlit) re-skinned clean-room from a diagnostic dashboard into an operational one — verdicts not predictions, decision-trace not Grad-CAM, no slide pixels — plus a live agent-choreography view (Level 1: component-state). Renders over the PHI-free telemetry; imports nothing from `atlas_patch`. See design D18. |
| 4 | `add-conductor-distribution` | Done | Wire the four logical agents as A2A peers (Google ADK + A2A), add the optional BigQuery telemetry backend, and the GUI Level 2 message-flow view. A2A earns its weight here as watchable choreography (design D8); the core already runs without it. |
| 5 | `add-conductor-data-lineage` | Done | DVC/Git data-lineage pipeline over the orchestrator's inputs/outputs. Additive layer — no rework of earlier phases. |
| 6 | `add-learned-recovery-classifier` | Done | Replace the rule-based failure classifier with one learned from the telemetry recovery dataset. The declarative task contract keeps this seam clean. |
| 7 | `add-compliance-dossier` | Done | Full EU AI Act / ISO 42001 compliance dossier building on the phase-2 Model Card and audit trail. |
| 8 | `add-gui-snapshot-contract` | Done | Freeze the Python→renderer seam: extend `export.py` to emit a versioned `snapshot.json` (run history, per-slide verdicts, decision trace, cohort metrics, derived Level-1/Level-2 choreography state) as the single machine-readable observability payload, round-trip verified (sink → reader → snapshot). Streamlit GUI untouched; a richer export ships even on its own. Contract-first half of the GUI redesign. ADD `gui-snapshot`, MODIFY `report-export`. |
| 9 | `redesign-observability-gui-react` | Done | Replace the Streamlit observability GUI with a refined React SPA (Vite/TS + Tailwind + shadcn/ui + 21st.dev; design system from taste + ui-ux-pro-max skills) rendering the phase-8 frozen snapshot — semantic verdict system, KPI stat-tiles, sortable verdict table, decision-trace tree, and agent-choreography with tasteful on-load motion — all within the unchanged read-only / no-pixel / no-score / PHI-free invariants, re-homed from Streamlit `AppTest` to Vitest + Playwright DOM guardrails. Prebuilt `dist/` vendored so `pip install` stays Node-free. Client-polling live choreography deferred to a possible later phase. MODIFY `observability-gui`. |
| 10 | `elevate-observability-gui-aesthetics` | Done | Raise the React GUI's perceived quality within the exact read-only / no-pixel / no-score / PHI-free envelope: a hero inline-SVG choreography flow graph (lit/idle node halos, one-shot `stroke-dashoffset` edge draws), a header with an aurora wash + logotype lockup, and lighter shared polish (cursor-tracking spotlight borders, hover-lift, verdict color-rail, spring-eased staggered entrance). CSS + inline SVG only — no new dependency, no `<img>`/`<canvas>`, no count-up. Promotes the motion-honesty rule (one-shot / interaction-driven only, never implies live data, off under `prefers-reduced-motion`) into a testable `observability-gui` requirement. MODIFY `observability-gui`. |

Phases 2–9 are additive follow-ons (design D17 for 2–4, the scope note for 5–7). Each is
kept out of the phase-1 change to keep it reviewable, falls on a capability-spec boundary,
and does not require retrofitting earlier work. Phases 8–9 re-render the phase-3
observability surface without touching its governance invariants: 8 freezes a snapshot
contract (the Python↔React seam), 9 rebuilds the renderer on it and retires the Streamlit
app. Phase boundaries: A1/A2/A3 are *internal slices* of phase 1 (commit + CI checkpoints in
one PR), not separate phases — splitting there would fragment specs mid-capability; phases
2–4 each add a whole capability; the 8/9 split falls on the frozen snapshot seam so the
renderer is always built against a stable contract.

## Constraints

- **Upstream untouched.** Orchestration phases do not modify `atlas_patch/` internals. The
  only integration surfaces are the CLI argv (to run work) and the documented HDF5 format
  at `<output>/patches/<stem>.h5` (to verify it).
- **Metadata-only, PHI-free telemetry.** No pixels, no embeddings, no HIPAA Safe-Harbor
  identifiers persisted — enforced by typed records and a write-time gate.
- **Operational, not clinical.** Validation checks structural correctness only; no
  diagnostic reasoning, keeping the layer out of Software-as-a-Medical-Device scope.
- **Optional heavy deps.** ADK / A2A / BigQuery live behind `atlas-patch[orchestrator]`;
  `pip install atlas-patch` is unchanged.
