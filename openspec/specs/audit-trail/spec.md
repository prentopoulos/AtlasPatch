# audit-trail Specification

## Purpose
TBD - created by archiving change add-conductor-governance. Update Purpose after archive.
## Requirements
### Requirement: Consequential actions are recorded in an append-only audit trail

The orchestrator SHALL append to a tamper-evident audit trail an entry for every consequential action — each dispatched execution, each recovery decision, each human-in-the-loop hold, approval, or unattended waiver, and each telemetry-gate rejection — sufficient to reconstruct after a run who or what authorized each irreversible or expensive action. Audit entries SHALL themselves be PHI-free, passing through the same pseudonymization and identifier-rejection as telemetry, so the audit trail cannot become a PHI side channel.

#### Scenario: An irreversible action's authorization is reconstructable

- **WHEN** a run applies a `force_reprocess` after confirmation (or under an unattended waiver) and its audit trail is inspected
- **THEN** the trail shows the action, the slide (pseudonymized), and whether it was authorized by a human confirmation or the unattended waiver

#### Scenario: A gate rejection is auditable

- **WHEN** the PHI write-gate rejects a record
- **THEN** an audit entry records that a rejection occurred and why, without reproducing the rejected identifier

#### Scenario: Audit entries carry no raw identifiers

- **WHEN** any audit entry is written for a slide
- **THEN** the slide appears pseudonymized and no Safe-Harbor identifier is present in the entry

### Requirement: The audit trail is tamper-evident via a hash chain

Each audit entry SHALL be linked to its predecessor by a cryptographic hash chain, such that any post-hoc edit, reordering, or deletion of an entry is detectable by verification. A verification routine SHALL walk the trail and report whether the chain is intact and, if not, the first broken link.

#### Scenario: An intact trail verifies

- **WHEN** an unmodified audit trail is verified
- **THEN** verification reports the chain intact

#### Scenario: An edited entry is detected

- **WHEN** any entry in the trail is altered after being written and the trail is verified
- **THEN** verification reports the chain broken and identifies the first affected entry

#### Scenario: A deleted entry is detected

- **WHEN** an entry is removed from the middle of the trail and the trail is verified
- **THEN** verification reports the chain broken at the point of removal
