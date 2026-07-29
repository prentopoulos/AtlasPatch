# System Card — `atlas_conductor`

> **Status:** Maintained. Finalized in the `add-conductor-governance` change (phase 2), when
> the governance guardrails this card describes were implemented and put under CI.
> This is a **system/orchestration card**, not a machine-learning model card: `atlas_conductor`
> contains **no trained model and no model inference on its decision path** (design decision D11).

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
  - As, or as part of, a **Software-as-a-Medical-Device**. The operational-only, no-inference-on-path
    boundary is what keeps it out of that scope; adding a diagnostic reasoner would void this card.
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
- **Failure classification is heuristic for the real adapter** (regex over torch vs.
  huggingface_hub stderr, in `atlas_conductor.recovery`) and is **best-effort**. Known limits:
  - Unknown / unmatched signatures default to **block, never blind-retry** (safe failure).
  - Stderr patterns can drift across library versions → the raw stderr tail is logged for human triage.
  - Coverage is measurable, not assumed: every classification is logged with its outcome (D14),
    and the fake adapter injects **labeled** failures so classifier accuracy is checked in CI.
- **Recovery actions are bounded** to AtlasPatch's own tuning knobs plus `--force`, quarantine, and
  block (D7); mutation ladders are monotone and capped by a per-item attempt budget.

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
| Retry loops burn GPU | Monotone mutation + per-item attempt budget |
| Coarse first-pass blast radius (one directory invocation) | Per-slide filesystem accounting; per-file recovery |
| PHI in slide stems | Pseudonymization + write-time Safe-Harbor gate (D12) |
| Safe-Harbor matcher is heuristic (identifier shapes) | Backstop only — pseudonymization is the primary control; fails closed on a match; the by-type invariant keeps clinical narrative out of records entirely |
| Late geometry-conflict discovery | Plan-time detection via the validity predicate |
| Audit trail edited after the fact | Hash chain makes any edit/deletion detectable via `verify_audit_chain` |

## 10. Deferred (tracked, not dropped)

Planned for follow-on changes: DVC/Git **data lineage** (phase 5), a **learned** recovery classifier
trained on the telemetry dataset (§4/D14, phase 6), and a full **EU AI Act / ISO 42001** compliance
dossier building on this card and the audit trail (phase 7).

---
_Template basis: Mitchell et al., "Model Cards for Model Reporting" (2019), adapted for a
non-ML orchestration system._
