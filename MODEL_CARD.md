# System Card — `atlas_conductor`

> **Status:** Maintained. Finalized in the `add-conductor-governance` change (phase 2), when
> the governance guardrails this card describes were implemented and put under CI; extended in
> `add-learned-recovery-classifier` (phase 6) with the optional learned recovery classifier (§4).
> This is a **system/orchestration card**, not a machine-learning model card: the orchestrator's
> **default decision path is deterministic with no trained model and no model inference** (design
> decision D11). The one optional learned component — an opt-in recovery-failure classifier
> (§4, D-LRC) — is a deterministic, operational-only classifier that reads tool stderr signatures
> and structural verdicts, never slide pixels, embeddings, or clinical content, and can never fall
> below the rule-based safety floor. It is off by default.

## 1. System details

| Field | Value |
|---|---|
| Name | `atlas_conductor` (console entry point `atlaspatch-conduct`, `atlas_conductor.cli:main`) |
| Owner / contact | Fork maintainer — `prentopoulos/AtlasPatch` (GitHub); see repository git history |
| Version | Ships with the `atlas_conductor` package in this repository (version tracks `atlas_patch.__version__`); governance guardrails added in phase 2 `add-conductor-governance` |
| Type | Deterministic operational orchestrator over the AtlasPatch CLI |
| Integration surfaces | **Only two:** AtlasPatch CLI argv (write) and the documented HDF5 at `<output>/patches/<stem>.h5` (read). No imports of `atlas_patch` internals. |
| Components | Planner, execution worker, validator, recovery (A2A peers); an in-process deterministic scheduler; a typed append-only telemetry sink; and the phase-2 governance gates (`atlas_conductor.governance`: PHI write-gate, HITL gate, tamper-evident audit trail) |
| License | Inherits the AtlasPatch repository license — CC-BY-NC-SA-4.0 (see `LICENSE`) |

## 2. Intended use

- **Primary use:** turn cohort-scale AtlasPatch runs into a structured, observable, resumable
  workflow — decide which CLI command produces a requested output, verify the HDF5 is
  structurally valid, classify failures, and recover within bounded, CLI-expressible actions.
- **Intended users:** researchers and operators running AtlasPatch preprocessing (segmentation,
  patch-coordinate extraction, feature embedding) over directories of whole-slide images.
- **Out-of-scope uses (do not use for):**
  - Any **clinical or diagnostic interpretation** of slide content. The system produces
    operational outcomes (`valid` / `skipped` / `quarantined` / `blocked`, with a structural
    reason code), never a diagnosis, finding, or clinical judgment (**D11**).
  - As, or as part of, a **Software-as-a-Medical-Device**. The operational-only boundary is what
    keeps it out of that scope: the system produces operational outcomes, never a diagnosis or
    clinical judgment. The optional learned classifier (§4) classifies *operational failure modes*
    only and does not change this boundary; adding a diagnostic reasoner would void this card.
  - Modifying the ML pipeline, the HDF5 format, or existing CLI behavior (all upstream-untouched
    by invariant).

## 3. Scope boundary (why this is not a diagnostic agent)

`atlas_conductor` sits at the **orchestration layer**, above AtlasPatch preprocessing and strictly
below any diagnostic reasoning. Contrast with behavior-cloning diagnostic agents such as
Pathology-CoT (arXiv 2510.04587), which pair a learned viewing policy with a vision-language model
to make clinical calls: that is a **different layer of the stack**. Placing such a reasoner on this
system's path would break the structural-not-clinical invariant, pull it into medical-device scope,
and create PHI-to-third-party disclosure. The boundary is therefore an **invariant, not a
preference** (D11).

## 4. Decision logic and its limits

- **Validation is structural only** (D4): a pure predicate over the HDF5 — opens; `coords` present,
  2-D, non-empty; required geometry attrs match; per-encoder feature dataset present, 2-D,
  row-aligned, NaN-free. It makes **no clinical judgment** about correctness of the tissue analysis.
- **Success = the validator confirms the requested output on disk** (D3). The CLI exit code gates
  only job/precondition failures; `--verbose` stderr is used **only to enrich failure
  classification**, never to decide success.
- **Failure classification runs behind one pluggable seam** (`atlas_conductor.classifier`,
  D-LRC-1): a `FailureClassifier` that consumes only the declarative `Outcome`/`Verdict`
  contracts and returns a `(classification, signature, confidence)` result the recovery proposer
  consumes unchanged. Two implementations sit behind it; **the rule-based one is the default**.
  - **Rule classifier (default):** the hand-written best-effort rules (regex over torch vs.
    huggingface_hub stderr, plus structural verdicts). Known limits: unknown / unmatched
    signatures default to **block, never blind-retry** (safe failure); stderr patterns can drift
    across library versions → the raw stderr tail is logged for human triage.
  - **Learned classifier (optional, opt-in — off by default):** a compact multinomial
    logistic-regression model trained offline from the PHI-free recovery dataset (`D-LRC-2..6`).
    It is **operational-only and PHI-free by construction** — its features are presence flags over
    a fixed operational stderr vocabulary, the structural verdict reason code, the exit-code sign,
    and the attempt bucket; it never sees slide pixels, embeddings, raw free-text stderr, slide
    stems, or paths, and the serialized artifact holds only coefficients over that fixed
    vocabulary. It is **deterministic** (fixed seed + fixed hyperparameters → a reproducible JSON
    artifact; inference is a pure `softmax`), so no generative or clinical reasoning enters the
    path. It carries a **safety floor** (D-LRC-4): it abstains to the rule classifier when its
    confidence is below a threshold, and a monotone-safety gate forbids it from turning a
    rule-blocked failure (`precondition-block` / `input-data` / `unknown`) into a retry — so it is
    **provably never less safe than the rules**, and `eval-classifier` reports a safety metric
    (fraction of should-block failures retried) that is 0 by construction and asserted in CI.
  - Coverage is measurable, not assumed: every classification is logged with its outcome (D14),
    and the fake adapter injects **labeled** failures so classifier accuracy and the safety metric
    are checked in CI against ground truth.
- **Recovery actions are bounded** to AtlasPatch's own tuning knobs plus `--force`, quarantine, and
  block (D7); mutation ladders are monotone and capped by a per-item attempt budget. The taxonomy
  and action ladder are identical regardless of which classifier is selected — only *how a failure
  is mapped to a classification* becomes learnable.

## 5. Human-in-the-loop (HITL)

HITL is applied **exactly where an action is irreversible or expensive**, not on every decision (D13).
The policy is a pure function of the action in `atlas_conductor.governance.hitl.requires_confirmation`,
consulted by the scheduler before the planner applies an action:

| Autonomous (within attempt budget) | Requires human confirmation |
|---|---|
| structural validation, skip-if-valid | `force_reprocess` (overwrites outputs) |
| `retry_as_is`, bounded `retry_with_mutation` | `block_job` (terminates work) |
| `mark_dependents_blocked`, `block_item` | `quarantine_item` |

An explicit **unattended-autonomy** mode (`JobConfig.unattended`) waives confirmation; when it does,
each action is still recorded in the audit trail as an authorized **waiver**. A held action is not
taken and the slide is recorded as `awaiting-confirmation`, so nothing is silently lost.

## 6. Privacy and PHI safeguards

- **Telemetry is PHI-free by construction** (D9 + D12): typed, append-only records with **no field
  able to hold an image, mask, or embedding**, slide stems **pseudonymized** before persistence
  (`atlas_conductor.governance.gate.PhiSafeSink` + `atlas_conductor.governance.phi.pseudonymize_stem`,
  a keyed HMAC that is stable within a run and unlinkable across runs), and a **deterministic
  write-time gate** that rejects any record whose free-text fields match a HIPAA Safe-Harbor
  identifier shape (`atlas_conductor.governance.phi.safe_harbor_findings`). A slide stem that is
  itself an MRN/accession is therefore pseudonymized — closing the "metadata-only ≠ identifier-free"
  gap — and a leaked identifier in a detail field is rejected fail-closed.
- **No PHI or pixel egress:** the system's only surfaces are CLI argv and on-disk HDF5; the optional
  BigQuery backend (phase 4) transmits only PHI-free typed records. A CI test asserts no telemetry or
  audit record type is array-capable, and a network-guard test asserts the core run opens no
  unexpected connection.
- **Compliance framing (honest):** these are **verifiable technical safeguards (necessary
  conditions)** with CI proofs — **not** a certification of legal HIPAA compliance, which further
  requires organizational, administrative, and physical safeguards (BAAs, risk assessments, access
  policy) outside this system's control.

## 7. Auditability

An **append-only, tamper-evident audit trail** (`atlas_conductor.governance.audit`) records every
dispatched action, recovery decision, HITL confirmation / hold / waiver, and telemetry-gate
rejection in a **hash chain**: each entry links to its predecessor, so any post-hoc edit, reordering,
or deletion is detectable by `verify_audit_chain`. Audit payloads are pseudonymized and scalar-only,
so the trail cannot become a PHI side channel. This is sufficient to reconstruct, after a run, who or
what authorized each consequential action, and to detect tampering — but it is tamper-*evidence*, not
tamper-*proofing* (WORM storage / cryptographic signing are out of scope).

## 8. Responsible-AI alignment

- **NIST AI RMF** (GOVERN / MAP / MEASURE / MANAGE) — governance and pre-deployment testing are
  encoded as the CI proofs above; the deterministic core removes generative-AI risks
  (confabulation, prompt injection) from the decision path entirely.
- **FDA / IMDRF GMLP** — the system is deliberately **non-SaMD** (§2–§3); the boundary is documented
  precisely so a reviewer can confirm it.
- **HITL / oversight** — see §5.

## 9. Known risks and mitigations (summary)

| Risk | Mitigation |
|---|---|
| Heuristic stderr classification is imperfect | Unknown → block; raw stderr logged; labeled fake-adapter failures test the logic in CI |
| Learned classifier overfits or drifts on novel stderr | Rules are the default; the abstention floor degrades an underconfident model *to the rules*, never below; opt-in only; `eval-classifier` surfaces the gap before enabling |
| A learned model turning a should-block failure into a retry | Monotone-safety gate forbids it categorically; safety metric = 0 asserted in CI; a vocabulary edit invalidating a model is caught by `feature_version` and falls back to rules |
| Retry loops burn GPU | Monotone mutation + per-item attempt budget |
| Coarse first-pass blast radius (one directory invocation) | Per-slide filesystem accounting; per-file recovery |
| PHI in slide stems | Pseudonymization + write-time Safe-Harbor gate (D12) |
| Safe-Harbor matcher is heuristic (identifier shapes) | Backstop only — pseudonymization is the primary control; fails closed on a match; the by-type invariant keeps clinical narrative out of records entirely |
| Late geometry-conflict discovery | Plan-time detection via the validity predicate |
| Audit trail edited after the fact | Hash chain makes any edit/deletion detectable via `verify_audit_chain` |

## 10. Deferred (tracked, not dropped)

Delivered since this card was first written: DVC/Git **data lineage** (phase 5) and the optional
**learned recovery classifier** trained on the telemetry dataset (§4/D14, phase 6). Still planned:
a full **EU AI Act / ISO 42001** compliance dossier building on this card and the audit trail
(phase 7), and a richer sklearn-backed learner behind the `orchestrator` extra (deferred; the seam
and JSON artifact format already admit it).

---
_Template basis: Mitchell et al., "Model Cards for Model Reporting" (2019), adapted for a
non-ML orchestration system._
