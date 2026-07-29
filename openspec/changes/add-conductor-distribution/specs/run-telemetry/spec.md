## MODIFIED Requirements

### Requirement: Append-only sink with pluggable backends
The telemetry layer SHALL expose one append-only sink interface with a local backend (jsonl or sqlite) as the default. It SHALL additionally provide an opt-in BigQuery backend implementing the same interface, selected only when explicitly configured (a backend selector plus a dataset), which maps each record family to a table and each typed record to a row insert. The BigQuery backend SHALL import its cloud client behind a guard and SHALL live in the `atlas-patch[orchestrator]` extra. Switching backends SHALL NOT change what any agent records: the same typed records flow through the same interface.

#### Scenario: Local backend is the default
- **WHEN** no telemetry backend is configured
- **THEN** events are appended to the local backend and the run does not require any cloud credentials

#### Scenario: BigQuery backend is opt-in behind the same interface
- **WHEN** the BigQuery backend is configured with a dataset
- **THEN** the same records are appended through the same interface as row inserts, with no change to the emitting agents

#### Scenario: BigQuery rows match the local rows
- **WHEN** a record is written through the BigQuery backend and through the local backend
- **THEN** the row inserted into the family's table equals the row the local backend serializes for that record (modulo the stamped timestamp), verifiable against a fake client with no live connection

#### Scenario: Core import graph stays cloud-free
- **WHEN** the core `atlaspatch` CLI is imported without the orchestrator extra
- **THEN** it imports no BigQuery client, and the default JSONL backend continues to work

## ADDED Requirements

### Requirement: Typed metadata-only message-flow family
The telemetry layer SHALL record a `message_flow` family capturing each inter-agent
interaction as a typed record `(job_id, from_agent, to_agent, message_type, correlation_id)`
with optional `slide_stem` and `stage`. Like the other families it SHALL be a frozen record of
scalars, enums, timestamps, and identifiers with no field able to hold a WSI image, tissue
mask, or embedding matrix, and its `slide_stem` SHALL flow through the same PHI-free write gate
as the other families. Recording `message_flow` SHALL NOT require any array-accepting method to
exist.

#### Scenario: Message flow is reconstructable and PHI-free
- **WHEN** a run records its inter-agent interactions
- **THEN** the `message_flow` family yields, per interaction, the ordered `(from_agent, to_agent, message_type, correlation)` tuple, and any persisted `slide_stem` is pseudonymized identically to the other families when the run gates it

#### Scenario: No array field on the new family
- **WHEN** any component records a `message_flow` interaction
- **THEN** the record type accepts only scalars, enums, timestamps, and identifiers, and there is no method that accepts an image or an array
