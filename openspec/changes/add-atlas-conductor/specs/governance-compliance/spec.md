## ADDED Requirements

### Requirement: Deterministic core, no clinical reasoning
The orchestrator SHALL make only operational decisions (which CLI command to run, whether an HDF5 output is structurally valid, whether and how to retry) and SHALL NOT perform, embed, or delegate any clinical or diagnostic interpretation of slide content. No vision-language model or other probabilistic reasoner SHALL be placed on the plan/dispatch/validate/recover path. This keeps the layer out of Software-as-a-Medical-Device scope and preserves the structural-not-clinical invariant by construction.

#### Scenario: No diagnostic verdict is ever produced
- **WHEN** the orchestrator completes a run and emits its summary
- **THEN** the summary reports per-slide operational outcomes (present/valid/missing/invalid/blocked) and never a clinical finding, diagnosis, or interpretation of tissue

#### Scenario: The decision path contains no model inference
- **WHEN** any planning, dispatch, validation, or recovery decision is taken
- **THEN** the decision is a deterministic function of filesystem state, exit codes, and typed outcomes, with no model inference call on the path

### Requirement: Telemetry is PHI-free by construction
The telemetry layer SHALL guarantee, by schema and a deterministic write-time gate, that no record can carry Protected Health Information. Slide identifiers (stems) SHALL be pseudonymized before persistence, and every record SHALL be rejected at write time if any field matches a HIPAA Safe-Harbor identifier pattern. This strengthens the metadata-only invariant from "no arrays" to "no identifiers."

#### Scenario: A PHI-bearing slide stem is blocked or pseudonymized
- **WHEN** a slide whose stem is or contains a name, MRN, or accession number reaches the telemetry sink
- **THEN** the stem is pseudonymized (or the record is rejected) and no raw identifier is written to the local or BigQuery backend

#### Scenario: Deterministic gate beats prompting
- **WHEN** a record containing a Safe-Harbor identifier is submitted to the sink
- **THEN** the write-time gate rejects it deterministically, independent of any model or heuristic judgment

### Requirement: No PHI or pixel data leaves the process boundary
The orchestrator SHALL make no network egress that carries slide pixels, tissue masks, embeddings, or PHI. Its only integration surfaces remain the AtlasPatch CLI argv and the on-disk HDF5. The optional BigQuery telemetry backend SHALL transmit only PHI-free typed records.

#### Scenario: Egress carries no protected content
- **WHEN** the orchestrator runs end to end
- **THEN** no outbound request contains image data, an embedding matrix, or a Safe-Harbor identifier, and a CI assertion confirms no unexpected external host is contacted

### Requirement: Human-in-the-loop gate on irreversible or expensive actions
The orchestrator SHALL require explicit human confirmation before executing any recovery action that overwrites existing outputs or terminates work — at minimum `force_reprocess`, `block_job`, and `quarantine_item` — unless the run is explicitly configured for unattended autonomy. Low-stakes actions (`retry_as_is`, bounded `retry_with_mutation`, `mark_dependents_blocked`) SHALL remain autonomous within their attempt budget.

#### Scenario: Force-reprocess pauses for confirmation
- **WHEN** recovery proposes `force_reprocess` for a slide with an existing HDF5
- **THEN** the action is held pending human confirmation and is not dispatched until confirmed, unless unattended mode is explicitly enabled

#### Scenario: Bounded retries stay autonomous
- **WHEN** recovery proposes a `retry_with_mutation` within the attempt budget
- **THEN** it proceeds without human confirmation

### Requirement: Audited append-only trail as compliance evidence
The orchestrator SHALL maintain an append-only audit trail recording every dispatched action, recovery decision, HITL confirmation, and telemetry gate rejection, sufficient to reconstruct after the fact who or what authorized each consequential action. The trail SHALL be tamper-evident (append-only, ordered).

#### Scenario: A run is auditable end to end
- **WHEN** a completed run's audit trail is inspected
- **THEN** each consequential action can be traced to its trigger, its classification, and — for gated actions — its confirming authority

### Requirement: Model Card describes the orchestrator's scope and limits
The change SHALL ship a Model Card (or system card) for the orchestrator stating its purpose, the operational-only scope, the structural-not-clinical validation boundary, known failure-classification limits, and the HITL and PHI safeguards, so that reviewers can assess it against responsible-AI expectations without reading the source.

#### Scenario: Reviewer assesses scope from the Model Card alone
- **WHEN** a reviewer reads the shipped Model Card without opening the source
- **THEN** they can determine the operational-only scope, the structural-not-clinical boundary, the known classification limits, and the HITL and PHI safeguards
