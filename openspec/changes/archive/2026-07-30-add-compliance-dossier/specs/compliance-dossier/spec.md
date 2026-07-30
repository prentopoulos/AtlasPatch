## ADDED Requirements

### Requirement: A maintained compliance dossier maps AI-governance obligations to implemented controls

The repository SHALL carry a maintained compliance dossier that positions `atlas_conductor`
against the EU AI Act and ISO/IEC 42001 and maps each applicable obligation to a concrete,
implemented control in this codebase. The dossier SHALL record a defensible **risk-tier
determination** — that the orchestrator is operational-only and non-Software-as-a-Medical-Device
(consistent with the System/Model Card's non-SaMD invariant), and therefore sits outside high-risk
scope, with the resulting obligations limited accordingly. For each obligation it addresses (EU AI
Act Annex IV technical-documentation elements — system description, intended purpose, risk
management, data governance, human oversight, accuracy/robustness, record-keeping/logging — and the
ISO/IEC 42001 management-system clauses / Annex A controls it maps), the dossier SHALL name the
implemented control that satisfies it and the CI proof that enforces it.

#### Scenario: The dossier states the risk-tier determination

- **WHEN** the dossier is read
- **THEN** it states that the system is operational-only and non-SaMD, that this places it outside
  high-risk / medical-device scope, and that the obligations it addresses follow from that
  determination — matching the System/Model Card's scope boundary

#### Scenario: Each addressed obligation names an implemented control and its proof

- **WHEN** any obligation row in the dossier is read
- **THEN** it names the framework obligation, the implemented control that satisfies it, and the CI
  test that enforces that control

### Requirement: The dossier stays honest about the limits of its compliance claims

The compliance dossier SHALL frame its contents as verifiable technical safeguards (necessary
conditions with CI proofs), and SHALL NOT claim legal conformity, a CE marking, an ISO/IEC 42001
certification, or any regulatory attestation the system cannot itself guarantee — which further
require organizational, administrative, and physical measures outside this system's control.

#### Scenario: The dossier disclaims certification

- **WHEN** the scope statement of the dossier is read
- **THEN** it distinguishes the system's verifiable technical safeguards from a legal conformity
  attestation or certification, and does not claim regulatory compliance the system cannot guarantee

### Requirement: The dossier is backed by a machine-checkable control register kept in sync by CI

The dossier's obligation→control→evidence mapping SHALL be sourced from a structured control register
committed to the repository, and a CI check SHALL keep the register and the rendered dossier in sync:
every control's cited evidence (module path and test node) SHALL resolve to something that exists in
the repository, the dossier SHALL contain no unresolved authoring placeholder, and every row in the
register SHALL appear in the rendered dossier. A released dossier therefore never cites a control that
was renamed or removed, and never ships with a `(to confirm)`-style stub.

#### Scenario: A register row citing a missing module or test fails the check

- **WHEN** the control register cites a module path or test node that does not exist in the repository
- **THEN** the CI check fails until the citation is corrected

#### Scenario: A dossier with unresolved placeholders fails the check

- **WHEN** the dossier contains a `(to confirm)` or equivalent placeholder marker
- **THEN** the CI check fails until the placeholder is resolved

#### Scenario: A register row missing from the dossier fails the check

- **WHEN** the register contains a control row that does not appear in the rendered dossier
- **THEN** the CI check fails until the dossier reflects every register row

#### Scenario: An in-sync dossier and register pass the check

- **WHEN** every register row appears in the dossier, every cited module/test resolves, and no
  placeholder remains
- **THEN** the CI check passes
