# System Card — `atlas_conductor`

> **Status:** DRAFT stub, authored during planning of the `add-atlas-conductor` change.
> Fields marked _(to confirm at implementation)_ are filled once the code lands.
> This is a **system/orchestration card**, not a machine-learning model card: `atlas_conductor`
> contains **no trained model and no model inference on its decision path** (design decision D11).

## 1. System details

| Field | Value |
|---|---|
| Name | `atlas_conductor` (entry point `atlaspatch-conduct`) |
| Owner / contact | _(to confirm at implementation)_ |
| Version | Tracks the `atlas-patch[orchestrator]` optional extra _(to confirm)_ |
| Type | Deterministic operational orchestrator over the AtlasPatch CLI |
| Integration surfaces | **Only two:** AtlasPatch CLI argv (write) and the documented HDF5 at `<output>/patches/<stem>.h5` (read). No imports of `atlas_patch` internals. |
| Components | Planner, execution worker, validator, recovery (A2A peers); an in-process deterministic scheduler; a typed append-only telemetry sink |
| License | Inherits the AtlasPatch repository license _(to confirm)_ |

## 2. Intended use

- **Primary use:** turn cohort-scale AtlasPatch runs into a structured, observable, resumable
  workflow — decide which CLI command produces a requested output, verify the HDF5 is
  structurally valid, classify failures, and recover within bounded, CLI-expressible actions.
- **Intended users:** researchers and operators running AtlasPatch preprocessing (segmentation,
  patch-coordinate extraction, feature embedding) over directories of whole-slide images.
- **Out-of-scope uses (do not use for):**
  - Any **clinical or diagnostic interpretation** of slide content. The system produces
    operational outcomes (`present` / `valid` / `missing` / `invalid` / `blocked`), never a
    diagnosis, finding, or clinical judgment (**D11**).
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
  huggingface_hub stderr) and is **best-effort**. Known limits:
  - Unknown / unmatched signatures default to **block, never blind-retry** (safe failure).
  - Stderr patterns can drift across library versions → the raw stderr tail is logged for human triage.
  - Coverage is measurable, not assumed: every classification is logged with its outcome (D14),
    and the fake adapter injects **labeled** failures so classifier accuracy is checked in CI.
- **Recovery actions are bounded** to AtlasPatch's own tuning knobs plus `--force`, quarantine, and
  block (D7); mutation ladders are monotone and capped by a per-item attempt budget.

## 5. Human-in-the-loop (HITL)

HITL is applied **exactly where an action is irreversible or expensive**, not on every decision (D13):

| Autonomous (within attempt budget) | Requires human confirmation |
|---|---|
| structural validation, skip-if-valid | `force_reprocess` (overwrites outputs) |
| `retry_as_is`, bounded `retry_with_mutation` | `block_job` (terminates work) |
| `mark_dependents_blocked` | `quarantine_item` |

An explicit **unattended-autonomy** mode can waive confirmation; when it does, each action is still
recorded in the audit trail with its authorizing configuration.

## 6. Privacy and PHI safeguards

- **Telemetry is PHI-free by construction** (D9 + D12): typed, append-only records with **no field
  able to hold an image, mask, or embedding**, slide stems **pseudonymized** before persistence, and
  a **deterministic write-time gate** that rejects any record matching a HIPAA Safe-Harbor
  identifier pattern. A slide stem that is itself an MRN/accession is therefore blocked or
  pseudonymized — closing the "metadata-only ≠ identifier-free" gap.
- **No PHI or pixel egress:** the system's only surfaces are CLI argv and on-disk HDF5; the optional
  BigQuery backend transmits only PHI-free typed records. A CI assertion confirms no unexpected
  external host is contacted.
- **Compliance framing (honest):** these are **verifiable technical safeguards (necessary
  conditions)** with CI proofs — **not** a certification of legal HIPAA compliance, which further
  requires organizational, administrative, and physical safeguards (BAAs, risk assessments, access
  policy) outside this system's control.

## 7. Auditability

An **append-only, tamper-evident audit trail** records every dispatched action, recovery decision,
HITL confirmation, and telemetry gate rejection, sufficient to reconstruct after a run who or what
authorized each consequential action.

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
| Late geometry-conflict discovery | Plan-time detection via the validity predicate |

## 10. Deferred (tracked, not dropped)

Planned for a follow-on change: DVC/Git **data lineage**, a **learned** recovery classifier trained
on the telemetry dataset (§4/D14), and a full **EU AI Act / ISO 42001** compliance dossier.

---
_Template basis: Mitchell et al., "Model Cards for Model Reporting" (2019), adapted for a
non-ML orchestration system._
