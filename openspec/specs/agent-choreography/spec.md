# agent-choreography Specification

## Purpose
TBD - created by archiving change add-conductor-gui. Update Purpose after archive.
## Requirements
### Requirement: Level-1 component-state view
The GUI SHALL provide a live component-state view of the four logical agents (planner,
worker, validator, recovery — and the scheduler loop), each rendered as active (lit) or idle
(dim). The active/idle state SHALL be derived by tailing the `agent_events` family, requiring
no A2A wiring and no change to the in-process components.

#### Scenario: Agents reflect recorded activity
- **WHEN** `agent_events` shows a given agent as the most recent actor for the run
- **THEN** that agent renders as active and agents with no recent event render as idle

#### Scenario: Works without A2A
- **WHEN** the choreography view renders for a run produced by the plain in-process components
- **THEN** it renders agent states from `agent_events` alone, with no dependency on an A2A transport

### Requirement: Now-processing ticker
The choreography view SHALL show a "now processing slide X · stage Y" ticker reflecting the
most recent `agent_events` row for the run, using the slide identifier exactly as persisted
(pseudonymized when the run gated it).

#### Scenario: Ticker follows the latest event
- **WHEN** the latest `agent_events` row names a slide and stage
- **THEN** the ticker shows that slide identifier and stage

#### Scenario: Ticker idles when no slide is active
- **WHEN** the latest event carries no slide/stage (e.g. planning or run completion)
- **THEN** the ticker shows an idle/summary state rather than a stale slide

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
