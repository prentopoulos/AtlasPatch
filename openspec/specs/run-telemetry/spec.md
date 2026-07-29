# run-telemetry Specification

## Purpose
TBD - created by archiving change add-atlas-conductor. Update Purpose after archive.
## Requirements
### Requirement: Operational metadata only
The telemetry layer SHALL persist operational metadata only — job status, per-slide stage and outcome, runtimes, validation results, and agent events. The telemetry record types SHALL NOT include any field capable of holding a WSI image, a tissue mask, or an embedding matrix, so that pixel or embedding data cannot be written even by mistake.

#### Scenario: No array-bearing record type exists
- **WHEN** any component attempts to record telemetry
- **THEN** the only available record types accept scalars, enums, timestamps, and identifiers, and there is no method that accepts an image or an array

#### Scenario: Embeddings stay on the filesystem
- **WHEN** a slide's features are produced and validated
- **THEN** telemetry records the validation result and metadata, while the feature matrix remains only in the AtlasPatch HDF5 on disk

### Requirement: Append-only sink with pluggable backends
The telemetry layer SHALL expose one append-only sink interface with a local backend (jsonl or sqlite) as the default. It SHALL additionally provide an opt-in BigQuery backend implementing the same interface, selected only when explicitly configured (a backend selector plus a dataset), which maps each record family to a table and each typed record to a row insert. The BigQuery backend SHALL import its cloud client behind a guard and SHALL live in the `atlas-patch[orchestrator]` extra. Switching backends SHALL NOT change what any agent records: the same typed records flow through the same interface.

#### Scenario: Local backend is the default
- **WHEN** no telemetry backend is configured
- **THEN** events are appended to the local backend and the run does not require any cloud credentials

#### Scenario: Alternative backend is opt-in behind the same interface
- **WHEN** an alternative backend (the BigQuery backend) is configured with a dataset
- **THEN** the same records are appended through the same interface as row inserts, with no change to the emitting agents

#### Scenario: BigQuery rows match the local rows
- **WHEN** a record is written through the BigQuery backend and through the local backend
- **THEN** the row inserted into the family's table equals the row the local backend serializes for that record (modulo the stamped timestamp), verifiable against a fake client with no live connection

#### Scenario: Core import graph stays cloud-free
- **WHEN** the core `atlaspatch` CLI is imported without the orchestrator extra
- **THEN** it imports no BigQuery client, and the default JSONL backend continues to work

### Requirement: Telemetry captures labeled recovery outcomes
Each `slide_stage_outcomes` and `agent_events` record SHALL carry enough structure to reconstruct, for every failure, the tuple `(failure-signature, classification, chosen action, whether the action resolved the failure)`. Over a run this makes the telemetry an append-only, labeled dataset of recovery attempts and their results — usable now to measure classification hit-rate, and later to train a learned classifier without changing the plan or dispatch code.

#### Scenario: A resolved retry is labeled as such
- **WHEN** a `resource-transient` OOM is retried with a smaller batch and the slide then validates
- **THEN** telemetry records the signature, the `resource-transient` classification, the `retry_with_mutation` action, and a resolved=true outcome

#### Scenario: Fake-adapter labeled failures form an eval cohort
- **WHEN** the fake adapter injects a labeled failure and recovery acts on it
- **THEN** telemetry records the injected label alongside the classification, so classifier accuracy can be measured against ground truth in CI

### Requirement: Record families cover the run
The telemetry layer SHALL record at least the families `jobs`, `slide_stage_outcomes`, `validation_results`, and `agent_events`, sufficient to reconstruct, after a run, which slides reached which stage, the outcome and reason for each, per-attempt runtimes, and the sequence of agent decisions.

#### Scenario: Run is reconstructable from telemetry
- **WHEN** a run completes and its telemetry is inspected
- **THEN** for each slide one can determine the stages attempted, the final outcome and reason, the per-attempt runtimes, and the recovery decisions taken

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
