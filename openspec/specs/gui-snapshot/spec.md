# gui-snapshot Specification

## Purpose
TBD - created by archiving change add-gui-snapshot-contract. Update Purpose after archive.
## Requirements
### Requirement: Single versioned observability snapshot

The conductor SHALL be able to assemble a telemetry directory into one JSON-safe snapshot
payload that is the single machine-readable contract for every observability renderer. The
payload SHALL carry a schema version identifier, and SHALL contain, per recorded run: the job
row (run history), the per-slide verdicts, the decision trace, the cohort metrics, and the
derived agent choreography and message-flow state. The snapshot SHALL be assembled from the
same PHI-free telemetry read path the GUI uses, and SHALL NOT import `atlas_patch` or require
a GPU, model weight, or slide file.

#### Scenario: Snapshot declares its schema version
- **WHEN** a snapshot is assembled for any telemetry directory
- **THEN** the payload carries a schema version identifier that a renderer can pin

#### Scenario: Snapshot contains every observability section per run
- **WHEN** a completed run's telemetry is assembled into a snapshot
- **THEN** the run's entry contains its job/history row, its per-slide verdicts, its decision
  trace, its cohort metrics, and its derived choreography and message-flow state

#### Scenario: Empty telemetry assembles without error
- **WHEN** no runs have been recorded in the telemetry directory
- **THEN** the snapshot assembles to a well-formed payload with its schema version and an empty
  set of runs, raising no exception

### Requirement: Verdicts are structural, carrying no clinical score

The snapshot SHALL present each slide's verdict as the validator's structural outcome — one of
valid, skipped, quarantined, or blocked — together with its reason code and human-readable
detail. It SHALL NOT contain any confidence, probability, or diagnostic score, and SHALL NOT
contain any slide pixel, tissue mask, heatmap, or embedding.

#### Scenario: Per-slide verdict is a structural outcome plus reason code
- **WHEN** the snapshot serializes a slide's verdict
- **THEN** it contains the structural outcome and its reason code, and contains no confidence,
  probability, or diagnostic score

#### Scenario: Snapshot carries no image or embedding data
- **WHEN** the snapshot is assembled for any run
- **THEN** it contains no slide pixel, mask, heatmap, or embedding value

### Requirement: Cohort metrics tally the terminal outcomes

For each run, the snapshot SHALL include cohort metrics giving the run's cohort size and its
valid, skipped, quarantined, and blocked tallies, consistent with the per-slide verdicts in
the same snapshot.

#### Scenario: Cohort tallies match the per-slide verdicts
- **WHEN** the snapshot is assembled for a run
- **THEN** the cohort metrics report the count of slides at each terminal outcome, and those
  counts equal the number of per-slide verdicts carrying that outcome

### Requirement: Derived choreography and message-flow state are serialized

The snapshot SHALL include, for each run, the Level-1 component-state choreography (which
agents are active versus idle and the now-processing indicator) and the Level-2 message-flow
state (the directed inter-agent edges with their counts), derived from the run's `agent_events`
and `message_flow` records. A run that recorded no message-flow records SHALL serialize a
message-flow state marked as having no flow, rather than raising or fabricating edges.

#### Scenario: Choreography state reflects the latest agent activity
- **WHEN** the snapshot serializes a run that recorded agent events
- **THEN** its choreography state marks the most-recent actor as active and the other agents as
  idle, and carries the now-processing indicator derived from the latest event

#### Scenario: Message-flow degrades cleanly when no flow was recorded
- **WHEN** the snapshot serializes a run that recorded no message-flow records
- **THEN** its message-flow state is marked as having no flow and carries no fabricated edges

### Requirement: PHI-free slide identity preserved through the snapshot

The snapshot SHALL display slide identifiers exactly as the telemetry persists them —
pseudonymized when the run gated its telemetry — and SHALL NOT reconstruct or contain any raw
identifier.

#### Scenario: Gated-run stems appear as their persisted pseudonyms
- **WHEN** a run persisted pseudonymized slide stems and is assembled into a snapshot
- **THEN** the snapshot contains those same pseudonyms and no raw slide identifier

### Requirement: Round-trip fidelity against the reader

The snapshot SHALL faithfully reproduce the recorded run state: assembling a snapshot from
telemetry records written to JSONL and read back through the read-only reader SHALL yield the
same per-slide verdicts, reason codes, cohort counts, decision trace, and derived state that
those records describe.

#### Scenario: Sink to snapshot round-trip preserves run state
- **WHEN** records written by the in-memory sink are persisted to JSONL, read back through the
  reader, and assembled into a snapshot
- **THEN** the snapshot's per-slide verdicts, reason codes, cohort counts, trace, and derived
  choreography and message-flow state match the recorded values
