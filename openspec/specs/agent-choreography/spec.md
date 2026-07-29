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

### Requirement: Level-2 message-flow is out of scope
The change SHALL NOT implement the Level-2 true A2A message-flow view (peer messages pulsing
as edges between agent nodes). That view depends on the phase-4 A2A wiring and is deferred.

#### Scenario: No message-flow edges are drawn
- **WHEN** the choreography view renders
- **THEN** it shows component-state (lit/dim) only and draws no inter-agent message edges
