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
| 1 | `add-atlas-conductor` | In progress | The orchestration layer: planner / worker / validator / recovery agents over the existing CLI + HDF5, with PHI-free telemetry, HITL gates, and by-construction governance. MVP scope: `segment-and-get-coords` and `process`. |
| 2 | `add-conductor-data-lineage` | Planned | DVC/Git data-lineage pipeline over the orchestrator's inputs/outputs. Additive layer — no rework of phase 1. |
| 3 | `add-learned-recovery-classifier` | Planned | Replace the rule-based failure classifier with one learned from the telemetry recovery dataset. The declarative task contract keeps this seam clean. |
| 4 | `add-compliance-dossier` | Planned | Full EU AI Act / ISO 42001 compliance dossier building on the phase-1 Model Card and audit trail. |

Phases 2–4 are the deferred follow-ons named in `add-atlas-conductor/design.md` (scope
note). They are intentionally out of the phase-1 change to keep it reviewable; each is
additive and does not require retrofitting earlier work.

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
