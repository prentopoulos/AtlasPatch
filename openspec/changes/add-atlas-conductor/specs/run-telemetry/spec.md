## ADDED Requirements

### Requirement: Operational metadata only
The telemetry layer SHALL persist operational metadata only — job status, per-slide stage and outcome, runtimes, validation results, and agent events. The telemetry record types SHALL NOT include any field capable of holding a WSI image, a tissue mask, or an embedding matrix, so that pixel or embedding data cannot be written even by mistake.

#### Scenario: No array-bearing record type exists
- **WHEN** any component attempts to record telemetry
- **THEN** the only available record types accept scalars, enums, timestamps, and identifiers, and there is no method that accepts an image or an array

#### Scenario: Embeddings stay on the filesystem
- **WHEN** a slide's features are produced and validated
- **THEN** telemetry records the validation result and metadata, while the feature matrix remains only in the AtlasPatch HDF5 on disk

### Requirement: Append-only sink with pluggable backends
The telemetry layer SHALL expose one append-only sink interface with a local backend (jsonl or sqlite) as the default and a BigQuery backend as an optional alternative. Switching backends SHALL NOT change what any agent records.

#### Scenario: Local backend is the default
- **WHEN** no telemetry backend is configured
- **THEN** events are appended to the local backend and the run does not require BigQuery credentials

#### Scenario: BigQuery is opt-in
- **WHEN** the BigQuery backend is configured
- **THEN** the same records are appended to BigQuery through the same interface, with no change to the emitting agents

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
