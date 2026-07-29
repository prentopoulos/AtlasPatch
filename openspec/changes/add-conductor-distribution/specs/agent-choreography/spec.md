## ADDED Requirements

### Requirement: Level-2 message-flow view
The GUI SHALL provide a Level-2 message-flow view rendering the four logical agents (and the
scheduler) as nodes with directed edges between them, each edge derived from the
`message_flow` telemetry family and pulsing on the recency of the latest message between that
pair. The view SHALL read the persisted `message_flow` family rather than subscribing to any
live transport, keeping the GUI a read-only tailer.

#### Scenario: Edges render from recorded messages
- **WHEN** a run has `message_flow` rows
- **THEN** the view draws a directed edge for each observed `(from_agent, to_agent)` pair and emphasizes the most recently active edge

#### Scenario: Populated for an in-process run
- **WHEN** the run was produced by the in-process transport (no live A2A network)
- **THEN** the Level-2 view still renders edges from the recorded `message_flow` family

### Requirement: Level-2 degrades to Level-1 when no message flow exists
When a run has no `message_flow` rows (for example a pre-phase-4 run or a run whose transport
recorded none), the Level-2 view SHALL degrade to an explicit Level-1-only state showing the
component-state nodes with no edges and a clear "no message flow recorded" indication, rather
than rendering a broken or empty graph.

#### Scenario: Older run without the family
- **WHEN** the selected run has no `message_flow` rows
- **THEN** the view shows the component-state nodes only, draws no edges, and indicates that no message flow was recorded for the run

## REMOVED Requirements

### Requirement: Level-2 message-flow is out of scope
**Reason**: The phase-4 A2A wiring and the `message_flow` telemetry family now exist, so the
Level-2 message-flow view is implemented in this change and superseded by the "Level-2
message-flow view" requirement above.
**Migration**: None. The Level-1 component-state view is unchanged; the Level-2 view is
additive and degrades to Level-1 for runs that recorded no message flow.
