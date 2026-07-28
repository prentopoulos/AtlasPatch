## 1. Package scaffolding and packaging

- [ ] 1.1 Create the `atlas_conductor/` top-level package (distinct from `atlas_patch/orchestration/`) with submodules for planning, dispatch, validation, recovery, telemetry, and agents.
- [ ] 1.2 Add the `atlaspatch-conduct` console entry point in `pyproject.toml`.
- [ ] 1.3 Add the optional extra `atlas-patch[orchestrator]` (Google ADK, A2A, `google-cloud-bigquery`, `pyyaml`) so the core install is unchanged; guard heavy imports so the core CLI never imports them.

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
- [ ] 6.4 Implement the HITL confirmation gate on `force_reprocess`/`block_job`/`quarantine_item`, with an explicit unattended-autonomy override (D13); record each decision to the audit trail.

## 7. Telemetry

- [ ] 7.1 Define the typed, append-only record families (`jobs`, `slide_stage_outcomes`, `validation_results`, `agent_events`) with no array/image field (enforces metadata-only by type) and the labeled recovery-outcome fields (D14).
- [ ] 7.4 Implement the PHI-free write-time gate: pseudonymize slide stems before persistence and reject any record matching a HIPAA Safe-Harbor identifier pattern (D12), shared by local and BigQuery backends.
- [ ] 7.2 Implement the local backend (jsonl or sqlite) as default.
- [ ] 7.3 Implement the optional BigQuery backend behind the same interface.

## 8. Agents and coordination

- [ ] 8.1 Wire planner, worker, validator, and recovery as A2A agents (Google ADK); keep the scheduler as an in-process loop.
- [ ] 8.2 Implement the terminal summary report driven by validator verdicts (per-slide outcome + reason + cohort counts).
- [ ] 8.3 Render the per-slide chain-of-decisions trace in the report and `--dry-run` (D15): ordered reconcile → dispatch → validate(reason) → recover per slide, summary-first with detail on demand, sourced from the audit-trail records (operational metadata only — no pixels/PHI).

## 9. Tests, CI, and docs

- [ ] 9.1 End-to-end no-GPU test: full planning → dispatch → validation → recovery → telemetry loop against the fake adapter, asserting the stage-granular recovery behavior (segment kept, only embed retried on injected OOM).
- [ ] 9.2 Tests for cohort-state reconciliation (the state × requested-output decision table) and for geometry-conflict blocking.
- [ ] 9.7 Tests for the input-admissibility gate (D16): `empty-cohort`, `no-wsi-files`, and `unreadable-input` each block before dispatch with no slide decode.
- [ ] 9.8 Test that the report/`--dry-run` decision trace (D15) surfaces the ordered per-slide decisions from the audit trail and carries operational metadata only (no pixels/PHI).
- [ ] 9.3 Add the no-GPU orchestrator loop to CI.
- [ ] 9.4 Write the orchestration-layer usage guide (YAML config, running with the fake adapter, reading the report) and add a README pointer.
- [ ] 9.5 CI: assert a PHI-laden slide stem injected via the fake adapter is pseudonymized or rejected and never persisted (D12); assert no egress carries pixels/PHI (D11 boundary).
- [ ] 9.6 CI: assert the HITL gate holds `force_reprocess`/`block_job` in attended mode and proceeds in unattended mode, with both paths recorded in the audit trail (D13).

## 10. Governance and compliance (by construction)

- [ ] 10.1 Implement the append-only, tamper-evident audit trail recording dispatched actions, recovery decisions, HITL confirmations, and telemetry gate rejections.
- [ ] 10.2 Implement the no-PHI/no-pixel egress assertion as a reusable check usable both at runtime and in CI.
- [ ] 10.3 Write the orchestrator Model Card (purpose, operational-only scope, structural-not-clinical boundary, classification limits, HITL + PHI safeguards).
- [ ] 10.4 Document the deferred follow-on scope (DVC/Git lineage, learned recovery classifier, EU AI Act / ISO 42001 dossier) so it is not silently dropped.
