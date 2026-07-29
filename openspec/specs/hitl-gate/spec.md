# hitl-gate Specification

## Purpose
TBD - created by archiving change add-conductor-governance. Update Purpose after archive.
## Requirements
### Requirement: Irreversible or expensive recovery actions require human confirmation

The orchestrator SHALL hold every irreversible or expensive recovery action — `force_reprocess` (overwrites existing outputs), `block_job` (terminates the whole run), and `quarantine_item` — for explicit human confirmation before it is applied, unless the run is in unattended mode. Bounded, non-destructive actions — `retry_as_is`, bounded `retry_with_mutation`, `mark_dependents_blocked`, `block_item`, structural validation, and skip — SHALL proceed autonomously without confirmation.

#### Scenario: A force-reprocess is held for confirmation

- **WHEN** recovery proposes `force_reprocess` for a slide in an attended run
- **THEN** the action is not applied until a human confirms it, and the slide is recorded as awaiting confirmation

#### Scenario: A bounded retry proceeds without confirmation

- **WHEN** recovery proposes a bounded `retry_with_mutation` within the attempt budget
- **THEN** the action is applied autonomously with no human prompt

#### Scenario: A denied confirmation does not apply the action

- **WHEN** an irreversible action is held and confirmation is denied (or unavailable, as in non-interactive CI)
- **THEN** the action is not taken and the slide's held state is recorded rather than lost

### Requirement: Unattended mode waives confirmation but records the waiver

When a run is explicitly configured as unattended, the orchestrator SHALL apply otherwise-gated irreversible actions autonomously, and SHALL record for each such action the authorizing unattended configuration in the audit trail, so that a later reviewer can see the action was taken under a standing waiver rather than a per-action human decision.

#### Scenario: Unattended run auto-approves and logs the authorization

- **WHEN** an irreversible action is proposed during an unattended run
- **THEN** the action is applied without a prompt, and the audit trail records that it was authorized by the unattended waiver

#### Scenario: The waiver is scoped to the run that set it

- **WHEN** a run without unattended mode encounters the same irreversible action
- **THEN** the action is held for confirmation, confirming the waiver does not carry across runs

### Requirement: The confirmation policy is a pure function of the action

The set of actions that require confirmation SHALL be a deterministic function of the recovery action alone, independent of slide content, timing, or environment, so the gate's behavior is testable and matches the policy documented in the System Card exactly.

#### Scenario: Policy classification is stable and content-independent

- **WHEN** the confirmation policy is queried for each recovery action in the taxonomy
- **THEN** `force_reprocess`, `block_job`, and `quarantine_item` require confirmation and every other action does not, regardless of which slide or run they arise in
