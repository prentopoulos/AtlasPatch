## 0. Delivery slices (phase 1 = the operational core; see design D17)

This change is **phase 1**: the deterministic operational core, built as three internal
vertical slices, each green-in-CI against the fake adapter before the next begins. A1
builds *minimal* forms of shared pieces (contracts, validator, fake adapter, scheduler);
A2/A3 enrich them. The four logical agents (planner / worker / validator / recovery) are
built here as **plain in-process typed components** coordinated by the scheduler — the A2A
protocol wiring is phase 4 (`add-conductor-distribution`), which the core does not need to
run (design D8).

- **Run A1 — walking skeleton (happy path):** 1.1, 1.2, 1.3, 2.1, 2.2, 2.4, 3.1, 3.3, 4.1, 4.2, 5.1, 5.3 *(valid-output path only)*, 5.4, 5.5 *(first pass only)*, 7.1, 7.2, 8.2, 9.1 *(happy-path assertion)*, 9.3. → *point at a cohort, watch it plan/run/report.*
- **Run A2 — reconciliation intelligence:** 2.3 *(Verdict reason codes)*, 3.2, 4.3, 4.5, 4.6, 5.2 *(real adapter, out of CI happy path)*, 8.3, 9.2, 9.7, 9.8. → *dry-run over a mixed cohort shows skip/run/block/geometry reasoning per slide.*
- **Run A3 — recovery:** 2.3 *(Classification / plan-delta / labeled fields)*, 4.4, 5.3 *(failure injection)*, 5.5 *(per-file recovery)*, 6.1, 6.2, 6.3, 9.1 *(recovery assertion)*, 9.4. → *injected OOM → segment kept, only embed retried.*

Later phases (own changes, see `PROJECT.md`): **phase 2** `add-conductor-governance`
(HITL gate, PHI-free write-gate, egress assertion, tamper-evident audit trail, Model Card);
**phase 3** `add-conductor-gui` (read-only observability GUI + Level 1 agent choreography,
design D18); **phase 4** `add-conductor-distribution` (A2A/ADK wiring, BigQuery backend,
GUI Level 2 message-flow). The phase-1 typed telemetry records (7.1) are the seam those
phases build on — the decision trace (8.3) reads them directly; phase 2's audit trail only
hardens their integrity, so it is not a prerequisite for phase 1.

## 1. Package scaffolding and packaging

- [ ] 1.1 Create the `atlas_conductor/` top-level package (distinct from `atlas_patch/orchestration/`) with submodules for planning, dispatch, validation, recovery, telemetry, and agents.
- [ ] 1.2 Add the `atlaspatch-conduct` console entry point in `pyproject.toml`.
- [ ] 1.3 Declare the optional extra `atlas-patch[orchestrator]` (Google ADK, A2A, `google-cloud-bigquery`, `pyyaml`) so the core install is unchanged, and guard heavy imports so the core CLI never imports them. Phase 1 itself needs only `pyyaml` + `h5py`; ADK/A2A/BigQuery are wired in phases 2/4.

## 2. Contracts (declarative data model)

- [ ] 2.1 Define the Plan and plan-node types (stage, targets, dependencies, decision, reason, attempt budget).
- [ ] 2.2 Define the adapter-agnostic Task type (stage, targets + expected HDF5 paths, geometry, encoders, tuning, attempt/mutation history, dependencies, idempotency key) — no argv, no fixture directive.
- [ ] 2.3 Define the raw Outcome, the per-slide Verdict, and the Classification/plan-delta types, including the labeled `(signature, classification, action, resolved?)` fields so telemetry is a recovery dataset (D14).
- [ ] 2.4 Define the YAML job-config schema and its loader/validator.

## 3. Output validation (build first — reused by the planner)

- [ ] 3.1 Implement the pure structural-validity predicate over the documented HDF5 format (opens; coords present/2-D/non-empty; required geometry attrs match; per-encoder feature dataset present, 2-D, row-aligned, NaN-free) using `h5py` only, no `atlas_patch` imports.
- [ ] 3.2 Emit reason codes distinguishing missing vs corrupt vs geometry-mismatch vs row-mismatch vs NaN.
- [ ] 3.3 Unit-test the predicate against fixture HDF5s covering every reason code and the fully-valid case.

## 4. Planner

- [ ] 4.1 Implement stage-DAG construction from a job config (segment → embed) and the stage→command dispatch mapping.
- [ ] 4.2 Implement state reconciliation: per-slide `skip`/`run`/`reuse`/`block` decisions from the validity predicate and requested output (branch-on-output).
- [ ] 4.3 Implement plan-time geometry-conflict blocking with actionable messages.
- [ ] 4.4 Implement plan-delta integration so the planner is the single writer of plan state (including `mark_dependents_blocked`).
- [ ] 4.5 (Optional, leaning yes) Implement `--dry-run` that prints the reconciled plan without dispatch.
- [ ] 4.6 Implement a plan-time input-admissibility gate (D16): reject empty cohorts, directories with no WSI-extension files, and unreadable/zero-byte inputs with actionable blocks and reason codes (`empty-cohort`, `no-wsi-files`, `unreadable-input`); keep checks shallow (extension/existence/size/optional magic bytes) — no slide decode.

## 5. Execution adapters and worker

- [ ] 5.1 Define the single `ExecutionAdapter` interface (`execute(task) -> Outcome`).
- [ ] 5.2 Implement the real adapter: build CLI argv from a task, run AtlasPatch as a subprocess, capture exit code, stdout/stderr tails, timing, produced paths.
- [ ] 5.3 Implement the fake adapter: write real canned HDF5s to expected paths; inject execution failures (CUDA-OOM, missing-token block) and structural-invalid outputs (row mismatch, NaNs, unopenable).
- [ ] 5.4 Implement the worker: forward raw unclassified outcomes only.
- [ ] 5.5 Implement the scheduler control loop: cohort-directory first pass, per-file recovery retries, per-slide filesystem accounting, concurrency governance.

## 6. Recovery

- [ ] 6.1 Implement two-source failure classification into the taxonomy (`resource-transient`, `precondition-block`, `input-data`, `structural-invalid`, `dependency-blocked`, `unknown`), including stderr-signature matching for the real adapter.
- [ ] 6.2 Implement the bounded, monotone recovery action set restricted to CLI tuning knobs + `--force` + quarantine/block, with per-item attempt budgets.
- [ ] 6.3 Implement `unknown → block` (never blind-retry) and downstream dependency-blocking proposals.

> The HITL confirmation gate on `force_reprocess`/`block_job`/`quarantine_item` (D13) is **phase 2** (`add-conductor-governance`). Phase 1 recovery proposes these actions; phase 2 gates the irreversible ones behind human confirmation.

## 7. Telemetry

- [ ] 7.1 Define the typed, append-only record families (`jobs`, `slide_stage_outcomes`, `validation_results`, `agent_events`) with no array/image field (enforces metadata-only by type) and the labeled recovery-outcome fields (D14).
- [ ] 7.2 Implement the local backend (jsonl or sqlite) as default.

> The PHI-free write-time gate (pseudonymize stems + reject HIPAA Safe-Harbor identifiers, D12) is **phase 2**; the optional BigQuery backend is **phase 4**. Both build on the 7.1 record types without changing them.

## 8. Coordination, report, and decision trace

- [ ] 8.2 Implement the terminal summary report driven by validator verdicts (per-slide outcome + reason + cohort counts).
- [ ] 8.3 Render the per-slide chain-of-decisions trace in the report and `--dry-run` (D15): ordered reconcile → dispatch → validate(reason) → recover per slide, summary-first with detail on demand, sourced from the typed telemetry records (`agent_events`/`slide_stage_outcomes`) — operational metadata only (no pixels/PHI).

> Wiring the four components as A2A peers (Google ADK) is **phase 4**; phase 1 coordinates the plain-class components with the in-process scheduler (5.5).

## 9. Tests, CI, and docs

- [ ] 9.1 End-to-end no-GPU test: full planning → dispatch → validation → recovery → telemetry loop against the fake adapter, asserting the stage-granular recovery behavior (segment kept, only embed retried on injected OOM).
- [ ] 9.2 Tests for cohort-state reconciliation (the state × requested-output decision table) and for geometry-conflict blocking.
- [ ] 9.7 Tests for the input-admissibility gate (D16): `empty-cohort`, `no-wsi-files`, and `unreadable-input` each block before dispatch with no slide decode.
- [ ] 9.8 Test that the report/`--dry-run` decision trace (D15) surfaces the ordered per-slide decisions from the typed telemetry records and carries operational metadata only (no pixels/PHI).
- [ ] 9.3 Add the no-GPU orchestrator loop to CI.
- [ ] 9.4 Write the orchestration-layer usage guide (YAML config, running with the fake adapter, reading the report) and add a README pointer.

> The governance CI proofs — PHI-gate rejection and HITL attended/unattended behavior — are **phase 2**, landing with the guardrails they verify.
