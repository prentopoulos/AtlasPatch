# Compliance dossier — `atlas_conductor`

This dossier positions the `atlas_conductor` orchestration layer against the **EU AI Act**
(technical-documentation elements, Annex IV) and **ISO/IEC 42001** (AI-management-system
clauses / Annex A controls), and maps each *applicable* obligation to a concrete, implemented
control in this codebase together with the CI test that enforces it.

It is the assessor-facing companion to the maintained **[System/Model Card](MODEL_CARD.md)**:
the card describes the system and its safeguards; this dossier arranges those same safeguards
against the obligations an assessor asks about. Every control below points at code that ships
and a test that runs in CI — the "provable, not asserted" thread that runs through the whole
project. The obligation→control→evidence rows are rendered from a machine-checkable control
register (`atlas_conductor/compliance/controls.yaml`); a CI check
(`tests/conductor/test_compliance_dossier.py`) resolves every cited module and test node,
forbids unresolved placeholders here, and asserts every register row appears in this document,
so the dossier cannot silently drift from the code.

## 1. Risk-tier determination

`atlas_conductor` is **operational-only and non-SaMD** (not Software-as-a-Medical-Device). It
plans, dispatches, validates, and recovers preprocessing runs over the existing AtlasPatch CLI
and the documented HDF5 format; it performs **no diagnostic or clinical reasoning** and its
validation checks *structural* correctness only. This matches the System/Model Card's scope
boundary (§2–§3) exactly.

Because of that determination the system sits **outside the EU AI Act's high-risk / medical-
device scope**, and the obligations that attach are correspondingly limited: it is not a
high-risk AI system, and the Annex IV elements below are addressed as *applicable* good-practice
documentation for an operational tool, not as a high-risk conformity submission. The
determination itself is the load-bearing argument of this dossier and is stated up front so a
reviewer can challenge it directly; if the system were ever extended into the decision path of a
diagnosis, this determination — and the obligations that follow — would have to be revisited.

## 2. Scope of these compliance claims (honest framing)

The controls documented here are **verifiable technical safeguards** — necessary conditions,
each with a CI proof. They are **not** a legal conformity attestation, a **CE marking**, an
**ISO/IEC 42001 certification**, or any regulatory attestation the system cannot itself
guarantee. Legal conformity and certification further require organizational, administrative,
and physical measures — Business Associate Agreements, risk assessments, access policy, a
deployed AI-management-system, independent audits — that are outside this system's control and
outside this dossier's scope. This restates the Model Card's §6 honesty framing and does not
contradict it: what the code can *prove* is presented as proof; what it cannot is named as out
of scope rather than claimed.

The register is the *checked minimum*. The dossier may add narrative around a control, but it
may never drop a registered control or cite one the code does not carry — CI enforces
register⊆dossier and resolves every citation.

## 3. EU AI Act — Annex IV technical-documentation elements

| ID | Clause | Obligation | Implemented control | Evidence (module · test) |
|----|--------|------------|---------------------|--------------------------|
| EU-AIA-01 | Annex IV §1 — general description & intended purpose | Document what the system is and its intended purpose. | The System/Model Card describes the orchestrator (planner/worker/validator/recovery over the existing CLI + HDF5) and its operational, non-diagnostic intended use. | `MODEL_CARD.md` · `tests/conductor/test_governance_model_card.py::test_model_card_exists` |
| EU-AIA-02 | Annex IV §1 — risk-tier determination (non-SaMD scope boundary) | State the system's risk classification and the boundary that fixes it. | The card records the non-SaMD, operational-only determination that places the system outside high-risk / medical-device scope, so the attaching obligations are limited. | `MODEL_CARD.md` · `tests/conductor/test_governance_model_card.py::test_model_card_states_the_non_samd_boundary` |
| EU-AIA-03 | Annex IV §2(g) / Art. 10 — data governance | Govern the data the system records; keep personal/clinical identifiers out. | The PHI-free write-gate pseudonymizes slide stems and rejects any record whose free-text matches a HIPAA Safe-Harbor identifier shape, fail-closed, before anything is persisted. | `atlas_conductor/governance/gate.py` · `tests/conductor/test_governance_phi.py::test_phi_laden_stem_injected_via_run_never_reaches_the_store` |
| EU-AIA-04 | Annex IV §2(e) / Art. 14 — human oversight | Ensure a human can oversee and intervene on consequential actions. | The HITL gate holds every irreversible/expensive recovery action for human confirmation in an attended run; an unattended run must explicitly waive, and the waiver is recorded. | `atlas_conductor/governance/hitl.py` · `tests/conductor/test_governance_hitl.py::test_force_reprocess_is_held_in_an_attended_run` |
| EU-AIA-05 | Annex IV §3 / Art. 15 — accuracy & robustness | Make the decision behaviour accurate and robust for its purpose. | The decision core is deterministic: a default run routes recovery through hand-written rules (no learned model in the path), so its behaviour is reproducible and inspectable. | `atlas_conductor/scheduler.py` · `tests/conductor/test_classifier_seam.py::test_default_scheduler_routes_through_the_rules` |
| EU-AIA-06 | Annex IV §2(g) / Art. 12 — record-keeping & logging | Automatically log events over the system's lifecycle in a tamper-evident way. | Every consequential action is appended to a hash-chained audit trail; any post-hoc edit, reorder, or deletion breaks the chain and is detected by `verify_audit_chain`. | `atlas_conductor/governance/audit.py` · `tests/conductor/test_governance_audit.py::test_edited_entry_is_detected_at_the_right_link` |
| EU-AIA-07 | Annex IV §2(b) / Art. 15 — robustness (no data egress) | Contain the system's outputs; do not leak pixels or personal data off-box. | Telemetry/audit record types are scalar-only (no array can hold a pixel/mask/embedding), and a core run opens no unexpected network connection. | `atlas_conductor/telemetry.py` · `tests/conductor/test_governance_phi.py::test_no_telemetry_or_audit_field_can_hold_an_array` |

## 4. ISO/IEC 42001 — AI-management-system clauses / Annex A controls

| ID | Clause | Obligation | Implemented control | Evidence (module · test) |
|----|--------|------------|---------------------|--------------------------|
| ISO-42001-01 | Clause 7.5 / A.3.2 — documented information (system documentation) | Maintain documented information describing the AI system and its management. | The System/Model Card is a governed, version-controlled document with a CI drift-check that forbids unresolved authoring placeholders. | `MODEL_CARD.md` · `tests/conductor/test_governance_model_card.py::test_model_card_has_no_unresolved_placeholder` |
| ISO-42001-02 | Clause 6.1 / A.5.2 — AI risk assessment | Identify AI-specific risks and their mitigations, proportionate to impact. | The card enumerates known risks and mitigations under an explicit non-SaMD determination that bounds the applicable risk surface. | `MODEL_CARD.md` · `tests/conductor/test_governance_model_card.py::test_model_card_states_the_non_samd_boundary` |
| ISO-42001-03 | A.7.4 — data quality & governance for AI systems | Govern data used and produced by the AI system, including sensitive data. | The PHI-free gate rejects a Safe-Harbor identifier surfacing in a free-text detail field, fail-closed, so identifiers never enter the persisted records. | `atlas_conductor/governance/phi.py` · `tests/conductor/test_governance_phi.py::test_identifier_in_detail_field_is_rejected_fail_closed` |
| ISO-42001-04 | A.9.2 — human oversight of the AI system | Provide for human oversight and a recorded decision on autonomous actions. | An unattended run waives HITL confirmation only explicitly, and the waiver is written to the audit trail so the oversight decision is always recoverable. | `atlas_conductor/governance/hitl.py` · `tests/conductor/test_governance_hitl.py::test_unattended_run_waives_confirmation_and_logs_the_waiver` |
| ISO-42001-05 | A.6.2.8 — AI system logging & event recording | Record events during operation so the system's behaviour can be examined later. | The audit trail records each action with a pseudonymized, scalar-only, PHI-free payload and verifies intact on an untampered run. | `atlas_conductor/governance/audit.py` · `tests/conductor/test_governance_audit.py::test_run_audit_entries_are_pseudonymized_and_phi_free` |

## 5. Per-run conformity evidence

The tables above are the *standing* dossier. For a specific completed run, the
`export-dossier <telemetry-dir> [--format json|html]` command assembles a **run-scoped
evidence bundle**: it re-verifies the run's audit chain with `verify_audit_chain` (reporting
**broken** rather than intact if the trail was tampered with), records the run's HITL
holds/approvals/waivers and telemetry-gate rejections, the per-slide operational outcomes and
cohort counts, and the control-register summary — all sourced from the same PHI-free
telemetry/audit read path the observability GUI and `export-report` use, so the bundle cannot
diverge from the report and carries no slide pixel, mask, embedding, or raw identifier.

## 6. Interpretation note

The EU AI Act Annex IV elements and ISO/IEC 42001 clauses do not map 1:1 onto an operational,
non-SaMD orchestrator; the mappings above are interpretive and address *applicable* obligations
under the §1 determination. This dossier does not claim exhaustive framework coverage or legal
conformity. Clause identifiers are given as the relevant management-system / technical-
documentation topic; a formal assessment would confirm the exact article/clause bindings for a
given deployment context.
