# model-card Specification

## Purpose
TBD - created by archiving change add-conductor-governance. Update Purpose after archive.
## Requirements
### Requirement: A maintained System/Model Card documents the system and its boundaries

The repository SHALL carry a maintained System/Model Card that documents the orchestrator's intended use, its users, its out-of-scope uses, the non-Software-as-a-Medical-Device scope boundary, the limits of its decision logic, its human-in-the-loop policy, and its privacy/PHI safeguards. The card SHALL state that the orchestrator's default decision path is deterministic with no trained model, and that the optional learned recovery classifier — when enabled — is a deterministic, operational-only component that classifies operational failure modes (from tool stderr signatures and structural verdicts) with no access to slide pixels, embeddings, or clinical content, and that it cannot fall below the rule-based safety floor. The card SHALL frame its safeguards as verifiable technical conditions, explicitly not a legal HIPAA or regulatory certification.

#### Scenario: The card states the non-SaMD boundary as an invariant

- **WHEN** the System/Model Card is read
- **THEN** it states that the system produces operational outcomes, never a diagnosis or clinical judgment, and that this boundary is what keeps it out of medical-device scope

#### Scenario: The card documents the learned classifier's operational-only scope

- **WHEN** the decision-logic section of the card is read
- **THEN** it describes the optional learned recovery classifier as operating only on operational signals (tool stderr and structural verdicts), never on slide content, and states that it abstains to the rule-based classifier and cannot be less safe than the rules

#### Scenario: The card is honest about the limits of its compliance claims

- **WHEN** the privacy section of the card is read
- **THEN** it distinguishes the system's verifiable technical safeguards from a legal certification, and does not claim regulatory compliance the system cannot guarantee

#### Scenario: The HITL policy in the card matches the implemented gate

- **WHEN** the human-in-the-loop section of the card is read against the shipped gate
- **THEN** the actions listed as requiring confirmation are exactly those the gate holds, and the autonomous actions match those it applies without a prompt

### Requirement: The System/Model Card is kept in sync with the shipped safeguards

The System/Model Card SHALL be verified in CI to contain no unresolved authoring placeholders, so a released card never ships with `(to confirm)`-style stubs, and each safeguard the card describes corresponds to an implemented safeguard in the codebase.

#### Scenario: A card with unfilled placeholders fails the check

- **WHEN** the card contains a `(to confirm)` or equivalent placeholder marker
- **THEN** the CI check fails until the placeholder is resolved

#### Scenario: A finalized card passes the check

- **WHEN** the card has every placeholder resolved and each described safeguard names an implemented module
- **THEN** the CI check passes
