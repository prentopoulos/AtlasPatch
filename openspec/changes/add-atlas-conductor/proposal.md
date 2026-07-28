## Why

AtlasPatch can process a slide or a directory, but at cohort scale the operational burden falls on the user: which command produces a given output, which slides succeeded or failed and why, whether a failure is safely retryable, whether the expected HDF5 outputs are actually present and well-formed, and whether a run can resume without repeating completed work. Today the CLI answers none of these — a directory run exits `0` even when individual slides fail, and per-slide `[FAIL]` lines appear only under `--verbose`. `atlas_conductor` adds a thin orchestration layer that turns those responsibilities into a structured, observable, resumable workflow **on top of** the existing CLI, without touching the ML pipeline.

## What Changes

- Add a new top-level package `atlas_conductor/` (distinct from AtlasPatch's internal `atlas_patch/orchestration/`) and a console entry point `atlaspatch-conduct`.
- Accept a **YAML job config** (cohort directory, requested output, encoder, patch geometry) and emit a **terminal summary report** plus append-only telemetry.
- Introduce four logical agents — **planner, execution worker, validator, recovery** — built as **plain in-process typed components** coordinated by the scheduler. (Wiring them as A2A peers on Google ADK is phase 4; the core needs no message bus to run — design D8.)
- **Plan in logical stages** (`segment` → `embed`, with `slide-encode`/`patient-encode` reserved for later) and dispatch them onto the coarser CLI commands via a stage→command map, so the orchestrator reasons at a finer grain than the CLI exposes.
- Integrate with AtlasPatch through **exactly two documented surfaces**: the CLI argv (to run work) and the HDF5 output format (to verify it). No imports of `atlas_patch` internals.
- Add a **mock/fixture execution adapter** satisfying the same interface as the real adapter, so the whole layer runs in CI with no GPU and no slides, including injectable failures (CUDA-OOM, missing-token block, row-count mismatch).
- Add an **append-only telemetry sink** — local (jsonl/sqlite) — storing operational metadata only, **metadata-only by construction** (typed record families with no array/image field), doubling as an **append-only labeled dataset of recovery outcomes** (`signature → classification → action → resolved?`) for later classifier learning. (The PHI-free write-gate — pseudonymized stems + HIPAA Safe-Harbor rejection — and the optional BigQuery backend build on these record types in later phases.)
- Preserve the **deterministic operational-only core** — no clinical reasoning, no model inference on the plan/dispatch/validate/recover path — keeping the layer out of Software-as-a-Medical-Device scope by construction.
- Package all heavy dependencies (ADK, A2A, BigQuery client) behind an optional extra `atlas-patch[orchestrator]` so `pip install atlas-patch` is unchanged.
- MVP scope is deliberately two commands: `segment-and-get-coords` and `process`.

### Phasing
This change is **phase 1 — the operational core**, delivered as internal slices A1 → A2 → A3 (design D17). The additive follow-ons are separate phases (see `PROJECT.md`): **phase 2** `add-conductor-governance` (HITL gate, PHI-free write-gate, egress assertion, audited trail, Model Card); **phase 3** `add-conductor-gui` (read-only observability GUI + live agent-choreography, re-skinned clean-room from a diagnostic dashboard — verdicts not predictions, decision-trace not Grad-CAM, no slide pixels; design D18); **phase 4** `add-conductor-distribution` (A2A/ADK wiring, BigQuery backend, GUI Level 2 message-flow). Each falls on a capability-spec boundary and requires no retrofit of phase 1.

## Capabilities

### New Capabilities
- `orchestration-run`: top-level run lifecycle — YAML job config intake, terminal summary report, the per-slide decision trace, and the hard boundary invariants (upstream untouched, CLI-only integration, structural-not-clinical validation, and the deterministic operational-only core with no model inference on the decision path).
- `job-planning`: reconcile current filesystem state against the requested output into a stage-DAG — skip-if-already-valid, branch-on-requested-output, geometry-conflict blocking, dependency edges.
- `execution-dispatch`: the worker and the adapter contract — real (subprocess CLI) and fake (canned HDF5) adapters behind one declarative task interface, with cohort-first-pass / per-file-recovery dispatch granularity.
- `output-validation`: a pure structural-validity predicate over the HDF5 outputs (opens, `coords` present and non-empty, feature rows align with coord rows, no NaNs), invoked both at plan time (skip decision) and post-run (verify).
- `failure-recovery`: classify failures from two sources (execution and validation) into a bounded taxonomy and choose an allowed recovery action drawn only from the CLI's own tuning flags, plus dependency-blocking of downstream stages.
- `run-telemetry`: an append-only operational-metadata sink with a local backend (jsonl/sqlite; BigQuery is phase 4), whose typed record families make the metadata-only invariant impossible to violate, and which captures labeled `(signature → classification → action → resolved?)` recovery outcomes.

_(The `governance-compliance` capability — PHI-free write-gate, HITL, egress assertion, audited trail, Model Card — moves to phase 2, `add-conductor-governance`. The deterministic operational-only core it depends on is retained here in `orchestration-run`.)_

### Modified Capabilities
<!-- None. AtlasPatch's existing specs and ML pipeline are untouched; openspec/specs/ is currently empty. -->

## Impact

- **New code**: `atlas_conductor/` package + `atlaspatch-conduct` entry point. No changes to `atlas_patch/`.
- **Dependencies**: the optional extra `atlas-patch[orchestrator]` is declared (Google ADK, A2A, `google-cloud-bigquery`, `pyyaml`); phase 1 imports only `pyyaml` + `h5py`, with ADK/A2A/BigQuery wired in phases 2/4. Core install unaffected.
- **Integration surface**: AtlasPatch CLI argv (write) and documented HDF5 format at `<output>/patches/<stem>.h5` (read) only.
- **CI**: a new no-GPU end-to-end path exercising planning → dispatch → validation → recovery → telemetry against the fake adapter.
- **Docs**: new usage guide for the orchestration layer; README pointer.
- **Delivery**: phase 1 ships as internal slices A1 (walking skeleton) → A2 (reconciliation intelligence) → A3 (recovery), each green-in-CI before the next (design D17). Governance, GUI, and distribution follow as phases 2–4 (`PROJECT.md`).
