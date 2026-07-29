## ADDED Requirements

### Requirement: One transport interface with in-process and A2A implementations
The orchestrator SHALL route the four logical agents (planner, worker, validator, recovery)
through a single `AgentTransport` interface with two implementations: an in-process transport
that calls the components directly (the default), and an A2A transport that exposes each agent
as a Google ADK / A2A peer. Selecting the transport SHALL NOT change any component's own code
path, and SHALL be chosen the same way the real/fake execution adapter is chosen.

#### Scenario: In-process transport is the default
- **WHEN** no transport is configured
- **THEN** the run uses the in-process transport, requires no cloud credentials and no A2A peers, and completes the full plan → dispatch → validate → report loop

#### Scenario: A2A transport is opt-in behind the same interface
- **WHEN** the A2A transport is configured
- **THEN** the same four agents run as A2A peers through the same interface, with no change to any agent's internal logic

### Requirement: Both transports produce identical run outputs
Running an identical job through the in-process transport and through the A2A transport SHALL
produce identical per-slide outcomes and identical telemetry family rows, modulo timestamps
and correlation identifiers. The transport SHALL be an observability and distribution layer
only; it SHALL NOT alter planning, dispatch, validation, recovery, or the scheduler's
governor decisions.

#### Scenario: Same job, same result across transports
- **WHEN** the same job is run through the in-process transport and through a stubbed A2A transport
- **THEN** the per-slide `RunResult` is identical and each telemetry family's rows match modulo timestamps and correlation ids

#### Scenario: Scheduler stays an in-process governor
- **WHEN** the A2A transport is active
- **THEN** the scheduler runs as the in-process resource governor routing tasks to the agent peers, and is not exposed as a fifth A2A agent

### Requirement: The transport emits the message-flow telemetry family
Every inter-agent interaction routed by a transport SHALL be recorded as one metadata-only
`message_flow` record capturing the ordered `(from_agent, to_agent, message_type,
correlation)` tuple. Both transports SHALL emit this family so the message-flow view is
populated for in-process runs, not only for live A2A runs.

#### Scenario: In-process run still records message flow
- **WHEN** a job runs on the in-process transport
- **THEN** a `message_flow` row is recorded for each routed inter-agent interaction, usable by the GUI Level-2 view with no A2A network present

#### Scenario: A2A run records the same family from real messages
- **WHEN** a job runs on the A2A transport and agents exchange peer messages
- **THEN** each message is recorded as a `message_flow` row of the same shape as the in-process transport emits

### Requirement: The A2A path stays behind the orchestrator extra and guarded imports
The A2A transport SHALL import `google-adk` and the A2A SDK only inside its own module, never
from the core CLI, the run façade, the telemetry core, or the in-process transport. The heavy
dependencies SHALL live in the `atlas-patch[orchestrator]` extra so `pip install atlas-patch`
and the core `atlaspatch` CLI import graph pull in neither.

#### Scenario: Core CLI imports no A2A dependency
- **WHEN** the core `atlaspatch` CLI module graph is imported without the orchestrator extra
- **THEN** it imports neither `google-adk` nor the A2A SDK, and the import-guard test asserts their absence

#### Scenario: Missing extra degrades to a clear error, not a core-import failure
- **WHEN** the A2A transport is selected but the orchestrator extra is not installed
- **THEN** selecting it raises a clear actionable error naming the extra, while the default in-process run remains unaffected
