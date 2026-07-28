## Context

AtlasPatch is a computational-pathology preprocessing tool. Its CLI (`atlas_patch/cli.py`) exposes per-slide/per-directory commands that segment tissue (SAM2), extract patch coordinates, and embed patch features into one canonical HDF5 per slide at `<output>/patches/<stem>.h5`. `atlas_conductor` is a brownfield extension that coordinates these commands at cohort scale. It does not modify the ML pipeline.

Grounding facts that drove the design (all verified against the current code):

- **The CLI's per-slide outcome signal is silent.** `main()` (cli.py:1310) maps `ClickException`→exit 1, `KeyboardInterrupt`→130, other→1, but **per-slide failures leave exit code 0**. `[FAIL] <name>: <err>` lines print only under `--verbose`, to stderr (`_echo_results`, cli.py:734). Exit code is therefore a *job/shard-level* signal, not a per-slide one.
- **The directory runner is resilient.** `ProcessingRunner.run` (`atlas_patch/orchestration/runner.py`) catches per-slide open/segmentation/extraction failures and continues, so a directory run yields a mix of valid and silently-missing HDF5s.
- **There is exactly one canonical HDF5 per slide stem** (`patch_h5_path`, `atlas_patch/core/paths.py:48`), no geometry in the filename. Skip-if-valid and branch-on-output both key off the same file inspected for different contents.
- **AtlasPatch already self-reconciles**: `--skip-existing` (default) plus `classify_existing_slide_output` (runner.py:75) gives skip/reuse/reprocess and raises `ClickException` on a patch-size/target-mag mismatch (cli.py:279). It writes per-slide lock files.
- **The HDF5 contract**: `coords` dataset `(N,5)`; `features/<enc>` `(N,D)` row-aligned; required int file attrs `patch_size_level0`, `patch_size`, `target_magnification` (`atlas_patch/utils/feature_h5.py:16`). AtlasPatch validates feature/coord row alignment but **never checks for NaNs** — that is genuinely additive.
- **The CLI takes a single `wsi_path`** (file or directory) — no arbitrary multi-file list — which constrains dispatch granularity.

There is a naming collision to avoid: `atlas_patch/orchestration/` is AtlasPatch's *internal* WSI parallelism. The new layer is named `atlas_conductor` to keep the hierarchy unambiguous.

## Goals / Non-Goals

**Goals:**
- Turn cohort-scale operation into a structured, observable, resumable workflow driven by decisions, not a fixed sequence.
- Make the engineering contribution the orchestrator's *decisions*: skip-if-already-valid, branch-on-requested-output, classify failures into retry-vs-block, and never schedule a stage whose upstream failed.
- Keep the entire layer runnable and testable with no GPU and no real slides via a fake adapter that shares the real adapter's interface and the validator's code path.
- Hold three invariants true *by construction*: (1) upstream ML pipeline untouched; (2) CLI + documented HDF5 are the only integration surfaces; (3) telemetry stores operational metadata only.

**Non-Goals:**
- Modifying SAM2 segmentation, coordinate generation, feature extraction, the HDF5 format, or any existing CLI behavior.
- Clinical/medical correctness. Validation checks *structural* correctness only.
- Commands beyond `segment-and-get-coords` and `process` (slide/patient encoding are reserved seams, not MVP work).
- Arbitrary-subset sharding via symlink/junction farms.
- A distributed scheduler or a persistent job server; the scheduler is an in-process control loop.

## Decisions

### D1 — Plan in logical stages, dispatch onto CLI commands
The plan is a DAG of logical stages (`segment` → `embed`); a stage→command map collapses them onto the coarser CLI (`process` = `{segment, embed}`; `segment-and-get-coords` = `{segment}`).
- **Why:** With only two commands where `process ⊇ segment-and-get-coords`, a command-level plan is a flat list — i.e. a linear runner, the explicit failure mode. Stage modeling makes recovery stage-granular and future-proofs the fan-in for `patient-encode`.
- **Alternative considered:** model raw commands. Rejected — simpler but collapses to a linear runner and cannot express "segmentation is done, only re-embed."

### D2 — Cohort-directory first pass, per-file recovery; per-slide accounting
First pass = one invocation per input directory; recovery/isolation retries = per-file invocation. Outcome accounting is always per-slide, from the filesystem, independent of dispatch granularity.
- **Why:** The CLI accepts only a single file-or-directory path, so arbitrary N-slide shards aren't natively expressible. Directory runs amortize the expensive SAM2 + encoder load; per-file retries are naturally surgical (point AtlasPatch at the one slide) with no symlink farm. The resilient directory runner + filesystem sweep already fits this shape.
- **Alternative considered:** per-slide dispatch throughout (clean attribution but reloads models per slide — brutal for the real adapter); symlink-farm sharding (Windows privilege + complexity for no MVP payoff).

### D3 — Validator/filesystem is the source of per-slide truth; stderr is a classification hint only
Success = the validator confirms the requested output is structurally valid on disk. Exit code gates only job/precondition-level failures; `--verbose` stderr is parsed only to *enrich* failure classification, never to decide success.
- **Why:** Exit-0-on-partial-failure and verbose-only `[FAIL]` lines make the CLI return untrustworthy for per-slide truth.

### D4 — One validity predicate, two call sites
"Is slide X's requested output present and structurally valid?" is a pure function over filesystem state, invoked at plan time (→ skip decision) and post-run (→ verify). Skip-if-valid is just validation run early.
- **Why:** Unifies the planner's skip logic and the validator's verify logic into one tested predicate.

### D5 — Fake adapter writes real (canned) HDF5 files
The fake adapter writes structurally real HDF5s to the expected paths and can inject both execution failures (nonzero exit / labeled stderr signature) and structural-invalid outputs (row mismatch, NaNs, unopenable file).
- **Why:** Makes the validator code path identical for real and fake, so structural checks and recovery are exercised in CI. A verdict-faking mock would leave the validator untested exactly where it matters.
- **Alternative considered:** return synthetic verdicts. Rejected — cheaper but hollow.

### D6 — Recovery classifies and proposes; the planner is the single writer of plan state
Recovery emits classification + proposed plan-deltas; the planner integrates them and owns the DAG, including marking downstream stages blocked when an upstream fails.
- **Why:** One owner of the graph = one place to enforce "don't schedule blocked dependents"; recovery stays a pure classifier.

### D7 — The recovery action space is exactly the CLI's tuning knobs
Allowed actions: `retry_as_is`, `retry_with_mutation` (monotone ladder over `--feature-batch-size`, `--seg-batch-size`, `--max-open-slides`, `--patch-workers`, `--feature-precision`), `force_reprocess` (`--force`), `quarantine_item`, `block_item`, `block_job`, `mark_dependents_blocked` — each with a bounded attempt budget carried in the plan.
- **Why:** Falls straight out of the CLI-only invariant and keeps the layer honest; AtlasPatch's own FAQ (OOM / slow) *is* the ladder. Bounds prevent GPU-burning retry loops; unknown/unclassified defaults to block, never blind-retry.

### D8 — Four A2A agents; scheduler is an in-process loop
Planner, worker, validator, recovery are A2A peers (Google ADK + A2A). The scheduler is a deterministic in-orchestrator resource governor, not a fifth agent.
- **Why:** Matches the decided MVP; the scheduler has no agentic payoff and adding it as an agent only enlarges the protocol surface and muddies review.

### D9 — Append-only, typed telemetry sink; metadata-only enforced by types
One sink interface with local (jsonl/sqlite) and BigQuery backends, over ~4 typed record families: `jobs`, `slide_stage_outcomes`, `validation_results`, `agent_events`. No record type has an array/image field.
- **Why:** Append-only keeps local and BQ structurally identical; typed records make invariant #3 unbreakable — there is no method that accepts pixels or an embedding matrix.

### D10 — Declarative, adapter-agnostic task contract
A task carries logical intent (stage, targets with expected HDF5 paths, geometry, encoders, tuning params, attempt/mutation history, dependencies, idempotency key) — **not** a pre-baked argv (real-specific) and **not** a fixture directive (fake-specific). Each adapter translates the task into its own action.
- **Why:** Keeps the real/fake seam clean and prevents adapter details leaking into the plan.

### D11 — Deterministic operational core; clinical reasoning is out of scope by invariant
The plan/dispatch/validate/recover path is a deterministic function of filesystem state, exit codes, and typed outcomes. No vision-language model or probabilistic reasoner is placed on it. Diagnostic interpretation of slide content is explicitly excluded.
- **Why:** This is the boundary that separates an *operational orchestrator* from a *diagnostic agent* (e.g. Pathology-CoT, arXiv 2510.04587, which pairs a learned viewing policy with a VLM to make clinical calls). Bolting such reasoning onto this layer would break the structural-not-clinical invariant, pull the tool into Software-as-a-Medical-Device (FDA) scope, and create PHI-to-third-party disclosure. Determinism is also what makes the governance guarantees provable — echoing the finding that *deterministic gates block 100% of violations where a prompt cannot*.
- **Alternative considered:** add a VLM reasoning stage à la Pathology-CoT. Rejected as an improper pairing — different layer of the stack, and fatal to the invariants.

### D12 — Telemetry is PHI-free by construction (extends D9)
Metadata-only is strengthened to identifier-free: slide stems are pseudonymized before persistence and a deterministic write-time gate rejects any record matching a HIPAA Safe-Harbor identifier pattern.
- **Why:** A slide *stem* can itself be an MRN or accession number, so "no arrays" did not by itself guarantee "no PHI." The typed schema already makes the metadata-only claim structural; extending it to identifiers closes the last gap and is CI-provable by injecting a PHI-laden stem via the fake adapter and asserting rejection.

### D13 — HITL gate on irreversible or expensive recovery actions (extends D7)
`force_reprocess`, `block_job`, and `quarantine_item` are held for human confirmation unless the run is explicitly unattended; bounded, non-destructive actions stay autonomous.
- **Why:** HITL belongs exactly where an action is irreversible or costly, not on every decision. Validation/skip/bounded-retry carry no such risk and should not pay a human-latency tax; overwriting or terminating work should.

### D14 — Telemetry doubles as a labeled recovery dataset; rule-based now, learned later (extends D5/D9)
Every failure is logged as `(signature, classification, action, resolved?)`. Classification stays rule-based for the MVP, but the log makes hit-rate measurable and lets a learned classifier replace the heuristics later without touching plan/dispatch (D10 keeps the seam clean).
- **Why:** This is the Pathology-CoT inversion applied to operations — replace a hand-coded policy with one learned from recorded traces. The fake adapter's *labeled* injected failures are the held-out eval cohort (the operational analogue of the paper's external validation cohort), so generalization across failure modes can be proven before the classifier is trusted on real slides.

## Scope note — baked in now vs. deferred
Baked into this change (load-bearing, painful to retrofit): D11–D14, the PHI-free telemetry gate, the HITL gate, the egress assertion, and the audited trail. Deferred to a clean follow-on change (additive layers, no rework): a DVC/Git data-lineage pipeline, a *learned* recovery classifier trained on the telemetry dataset, and a full EU AI Act / ISO 42001 compliance dossier.

## Risks / Trade-offs

- **Real-adapter failure classification is heuristic** (regex over torch vs huggingface_hub stderr). → Default unknown/unclassified to `block`, never retry; the fake adapter injects *labeled* failures so recovery logic is deterministically tested; treat the taxonomy mapping as best-effort and log the raw stderr tail for human triage.
- **Retry ladders can oscillate or loop.** → Monotone mutation (values only shrink) + explicit per-item attempt budget in the plan contract, not a magic constant in the agent.
- **Cohort-directory first pass gives coarse blast radius** (one invocation, many slides). → The runner's per-slide resilience + filesystem sweep localize outcomes; recovery re-runs only the missing/invalid slides per-file.
- **Job configs listing arbitrary files not under one directory** aren't natively dispatchable. → MVP requires the cohort to be a directory (matching AtlasPatch's directory mode and the SLURM `WSI_ROOT` pattern); link-farm support is a documented later enhancement.
- **Geometry conflict against an existing HDF5 is a block, discovered late by AtlasPatch.** → The planner detects patch-size/target-mag mismatch at plan time via the validity predicate and blocks the item with an actionable message before dispatch.
- **Naming/packaging drift into core.** → Separate `atlas_conductor/` package, separate entry point, heavy deps behind `atlas-patch[orchestrator]`; core install untouched.

## Migration Plan

Additive only; no migration of existing data or behavior. Rollout: land the package + optional extra, wire the CI no-GPU path against the fake adapter, then document the entry point. Rollback = remove the package and extra; AtlasPatch is unaffected because nothing in `atlas_patch/` changes.

## Open Questions

- BigQuery record families: keep the 4 proposed, or split `agent_events` into `agent_messages` vs `agent_decisions`?
- Should the terminal report have a machine-readable sibling (JSON) in MVP, or is human-readable enough?
- Idempotency key composition — `(job_id, slide_stem, stage, geometry, encoder)` — is that sufficient to make resume safe across config edits?
- Do we expose a `--dry-run` that prints the reconciled plan (planner only, no dispatch) in MVP? (Leaning yes — it's cheap and demonstrates the decision surface.)
