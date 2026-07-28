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
- **Justification for the protocol (added):** the deterministic core (D11) does not *need* A2A for correctness — the four components would produce identical outputs as plain in-process calls. The protocol earns its weight as an **observability/demonstration** payoff: the real inter-agent messages are exactly what the GUI's live message-flow view (Level 2, D18) renders. Delivery therefore builds the core as plain typed components first (Runs A1–A3) and wires A2A last (Run C), so the protocol is adopted for a named reason — watchable choreography — rather than by default. See D17 for the delivery slicing.

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

### D15 — Chain-of-decisions trace is a first-class report output (extends D3/D14, feeds task 8.2)
The terminal report and `--dry-run` render, per slide, the *ordered decisions* that produced the outcome — reconcile → dispatch → validate (reason code) → recover — not just the final verdict and cohort counts.
- **Why:** The thesis is that the contribution is the orchestrator's *decisions* (D1–D7); a report that shows only outcomes asserts that thesis without demonstrating it. The trace makes the decision surface the visible artifact and turns `--dry-run` into the primary demonstration ("what I'd do to N slides and why, touching nothing"). It is near-free: every decision is already written to the audit trail (task 10.1), so this is a rendering concern, not new computation.
- **Boundary:** Operational metadata only — same PHI-free, no-pixel constraints as D9/D11/D12 (pseudonymized stems, reason codes, tuning deltas). Verbosity is controlled by summary-first output with per-slide detail on demand (dry-run / failures / opt-in).
- **Provenance:** the reasoning-trace *presentation* pattern is adapted clean-room (idea only — no code, weights, or data) from NV-Reason-CXR-3B's "show the work" chain-of-thought; here the checklist is operational (config/geometry/state/dispatch/validate/recover), never clinical, preserving D11.

### D16 — Plan-time input-admissibility gate; shallow, not deep (extends D2/D4)
Before dispatch, the planner rejects inadmissible cohorts/inputs — empty cohort, no WSI-extension files, unreadable/zero-byte files — with an actionable block and a reason code (`empty-cohort`, `no-wsi-files`, `unreadable-input`), rather than dispatching and inheriting a silent per-slide failure.
- **Why:** Without a front-door guard, a non-WSI or empty cohort reproduces exactly the silent exit-0 / missing-HDF5 failure this layer exists to eliminate. Catching it at plan time moves the failure from "late, mysterious, per-slide" to "early, structured, actionable" — on-thesis with D3/D4.
- **Boundary — shallow by construction:** admissibility is a cheap check (extension allowlist + existence + non-zero size + optional magic bytes), *not* a slide decode. Deep WSI validation would need a slide-reader dependency and start reimplementing pipeline responsibilities, brushing the "don't reach into `atlas_patch`" invariant. Deep validation stays AtlasPatch's job; the gate only rejects obvious garbage.
- **Provenance:** the out-of-distribution-rejection lesson is adapted (idea only) from the MedVision-AI failure mode (a non-chest image classified "pneumonia, 87.3%") — the operational analogue is refusing to confidently process input the pipeline cannot consume.

### D17 — Deliver in vertical slices, not one 44-task change
The work ships as a sequence of runs — **A1 → A2 → A3 → GUI → B → C** — where each run is a *vertical slice* that goes config → plan → dispatch → validate → report **end-to-end, green in CI against the fake adapter**, and each successive run adds one increment of *decision sophistication*.
- **A1 — walking skeleton (happy path):** minimal contracts, the validity predicate, a valid-output-only fake adapter, a trivial skip-vs-run planner, first-pass scheduler, typed local telemetry, terminal report. Demonstrates "point at a cohort, watch it plan/run/report."
- **A2 — reconciliation intelligence:** branch-on-requested-output, skip-if-valid on partial cohorts, geometry-conflict block, input-admissibility gate (D16), `--dry-run`, full validator reason codes, the decision-trace render (D15), the real subprocess adapter (kept out of the CI happy path). Demonstrates the "decisions are the contribution" thesis.
- **A3 — recovery:** fake-adapter failure injection, two-source classification, the bounded monotone action ladder, `unknown → block`, dependency-blocking, per-file recovery retries. Completes the loop.
- **GUI — read-only observability** (D18), attachable right after A1 and grown across A2/A3.
- **B — governance:** HITL gate, PHI-free write gate, tamper-evident audit trail, egress assertion, Model Card, and the CI proofs.
- **C — distribution:** A2A/ADK agent wiring, BigQuery backend.
- **Why:** 44 tasks landing (or failing) as one unit is not a tractable implement/review unit; vertical slices are each independently demonstrable and green, and A1 is the fastest path to "in motion." Splitting by *workstream* (a "validator run," a "planner run") was rejected — those runs don't execute on their own.
- **End result is unchanged:** the union A1 ∪ A2 ∪ A3 ∪ B ∪ C equals the original scope; slicing changes delivery order, review size, and when CI goes green — not the final feature set or any of D1–D16. The GUI is the one net addition, and it was requested independently of the split.
- **Load-bearing caveat:** the **validity predicate** (task 3.1) and the **typed telemetry record shapes** (task 7.1) must be correct in A1, because every later run — planner decisions, the decision trace, the GUI, the PHI gate — renders or gates off them. Get the *record types* right early so B's PHI gate is a write-time filter in front of an already-metadata-only sink (additive), not a retrofit.

### D18 — Read-only observability GUI, re-skinned from a diagnostic template, with live agent choreography
A Streamlit GUI is added as an **additive renderer** over the PHI-free telemetry sink + the recorded decision events — another renderer alongside the terminal report / `--dry-run` trace (D15). It imports nothing from `atlas_patch`, reads only those records, and **tails** the append-only sink rather than hooking the orchestrator process, so it corrupts no invariant. **Read-only for the MVP** (observe runs, verdicts, decision traces, metrics, history); it is *not* a control surface — HITL confirmation (D13) and job submission are later work.
- **Re-skin, not clone.** The *ergonomics* are adapted clean-room (idea only — no code, weights, or data) from MedVision-AI's Streamlit dashboard — the same project D16 cites as a cautionary failure — but every panel **inverts from clinical to operational**:

  | MedVision-AI (diagnostic) | atlas_conductor GUI (operational) |
  |---|---|
  | Upload X-ray image | Point at / submit a YAML job config — never upload the WSI |
  | "Pneumonia 87.3%" prediction + confidence | Per-slide **verdict** + reason code (valid / missing / corrupt / geometry-mismatch / blocked) — **no probability** |
  | Grad-CAM heatmap over pixels | The **D15 chain-of-decisions trace** — the decision trace *is* the Grad-CAM analogue |
  | Threshold slider | Recovery-ladder / tuning config (and later the HITL confirm) |
  | ROC-AUC / metrics | Operational run metrics — recovery hit-rate is the honest ROC-AUC analogue (D14) |
  | Download research report | HTML/JSON sibling of the terminal report |
  | Session history | Job / run history from the telemetry sink |
  | *Displays the X-ray* | **Dropped entirely — no slide pixels, ever** |

- **Three hard guardrails** (the places a well-meaning GUI silently becomes a medical device): (1) **never render slide pixels** — no-pixel egress (D11/D15); (2) **verdict, not prediction** — deterministic reason codes, no confidence score anywhere; (3) **"metrics" = operational metrics only**, never a clinical-accuracy claim.
- **Live agent choreography** — a real-time view of which agents are engaged, in two fidelity levels:
  - **Level 1 — component-state panel:** agents rendered lit (active) / dim (idle) with a "now processing slide X · stage Y" ticker, driven by tailing the `agent_events` record family (task 7.1). Works **from A1** with plain-class components; needs no A2A.
  - **Level 2 — true A2A message-flow:** peer messages / handoffs pulse as edges between agent nodes. Needs Run C's A2A wiring, and is the **named justification** for adopting the protocol (see D8).
  - All `agent_events` are operational metadata (agent id, stage, pseudonymized stem, timestamps, reason code) — PHI-free, under the same guardrails above.
- **Sequencing:** GUI + Level 1 attach after A1 (fastest "in motion" demo); Level 2 lands with Run C.
- **Provenance:** presentation ergonomics adapted clean-room from MedVision-AI (idea only); all semantics operational, preserving D11.

## Scope note — delivery ordering (supersedes "baked in now")
Ordering is per **D17**: the deterministic core lands first (A1–A3), the observability GUI attaches after A1, governance hardening follows in Run B, distribution (A2A + BigQuery) in Run C. What is **load-bearing in A1 and cannot be deferred**: the validity predicate (3.1) and the typed telemetry record shapes (7.1) — everything downstream renders or gates off them. What is **honored throughout by construction, not as a task**: D11 (deterministic operational core). What **lands as its own run but is still in-scope**: D12 PHI-free gate and the egress/audit hardening (Run B), D13 HITL (Run B), the D14 labeled-outcome fields (A3 onward). **Deferred to clean follow-on changes** (additive, no rework): a DVC/Git data-lineage pipeline, a *learned* recovery classifier trained on the telemetry dataset, and a full EU AI Act / ISO 42001 compliance dossier.

## Risks / Trade-offs

- **Real-adapter failure classification is heuristic** (regex over torch vs huggingface_hub stderr). → Default unknown/unclassified to `block`, never retry; the fake adapter injects *labeled* failures so recovery logic is deterministically tested; treat the taxonomy mapping as best-effort and log the raw stderr tail for human triage.
- **Retry ladders can oscillate or loop.** → Monotone mutation (values only shrink) + explicit per-item attempt budget in the plan contract, not a magic constant in the agent.
- **Cohort-directory first pass gives coarse blast radius** (one invocation, many slides). → The runner's per-slide resilience + filesystem sweep localize outcomes; recovery re-runs only the missing/invalid slides per-file.
- **Job configs listing arbitrary files not under one directory** aren't natively dispatchable. → MVP requires the cohort to be a directory (matching AtlasPatch's directory mode and the SLURM `WSI_ROOT` pattern); link-farm support is a documented later enhancement.
- **Geometry conflict against an existing HDF5 is a block, discovered late by AtlasPatch.** → The planner detects patch-size/target-mag mismatch at plan time via the validity predicate and blocks the item with an actionable message before dispatch.
- **Naming/packaging drift into core.** → Separate `atlas_conductor/` package, separate entry point, heavy deps behind `atlas-patch[orchestrator]`; core install untouched.
- **Input-admissibility gate could creep toward re-validating slides (D16).** → Keep it shallow (extension allowlist + existence + size + optional magic bytes); deep decode stays AtlasPatch's responsibility, preserving the no-reach-into-pipeline invariant.

## Migration Plan

Additive only; no migration of existing data or behavior. Rollout: land the package + optional extra, wire the CI no-GPU path against the fake adapter, then document the entry point. Rollback = remove the package and extra; AtlasPatch is unaffected because nothing in `atlas_patch/` changes.

## Open Questions

- BigQuery record families: keep the 4 proposed, or split `agent_events` into `agent_messages` vs `agent_decisions`? (The Level 2 message-flow view in D18 leans toward a clean `agent_messages` vs `agent_decisions` split, since the choreography visual renders *messages* while the decision trace renders *decisions* — revisit when Run C wires A2A.)
- ~~Should the terminal report have a machine-readable sibling (JSON)?~~ **Resolved (D18):** yes — an HTML/JSON sibling of the report is a GUI-run task; it is the same audit/telemetry data in another shape.
- Idempotency key composition — `(job_id, slide_stem, stage, geometry, encoder)` — is that sufficient to make resume safe across config edits?
- ~~Do we expose a `--dry-run`?~~ **Resolved (D17):** yes — `--dry-run` lands in Run A2; it's the primary demonstration of the decision surface.
