# execution-dispatch Specification

## Purpose
TBD - created by archiving change add-atlas-conductor. Update Purpose after archive.
## Requirements
### Requirement: Adapter-agnostic task contract
A dispatched task SHALL carry only declarative intent: stage, target slide(s) with their expected HDF5 output paths, geometry, encoder(s), tuning parameters, attempt number, mutation history, upstream dependencies, and an idempotency key. A task SHALL NOT carry a pre-built CLI argv string or a fixture directive; each adapter SHALL translate the task into its own action.

#### Scenario: The same task drives either adapter
- **WHEN** an identical task is handed to the real adapter and to the fake adapter
- **THEN** each produces its own action (subprocess argv vs canned output) from the task's declarative fields alone, with no adapter-specific field baked into the task

### Requirement: Real and fake adapters share one interface
The execution layer SHALL define a single adapter interface with two implementations: a real adapter that invokes the AtlasPatch CLI as a subprocess and captures exit code, stdout tail, stderr tail, and timing; and a fake adapter that satisfies the same interface without a GPU or real slides. Selecting the adapter SHALL NOT change any other agent's code path.

#### Scenario: Mock mode runs the full loop without hardware
- **WHEN** the orchestrator is configured to use the fake adapter
- **THEN** planning, dispatch, validation, recovery, and telemetry all execute unchanged and the run completes with no GPU and no real slide files

### Requirement: Fake adapter emits real outputs and injectable failures
The fake adapter SHALL write structurally real HDF5 files to the tasks' expected output paths for successful targets, and SHALL be able to inject, per target, an execution failure (nonzero exit with a labeled stderr signature) or a structurally invalid output (for example feature/coord row-count mismatch, NaN-bearing features, or an unopenable file).

#### Scenario: Injected CUDA-OOM execution failure
- **WHEN** the fake adapter is directed to fail a target with a CUDA-OOM signature
- **THEN** it returns a nonzero outcome whose stderr tail carries the OOM signature and writes no valid output for that target

#### Scenario: Injected row-count mismatch
- **WHEN** the fake adapter is directed to emit a row-count mismatch for a target
- **THEN** it writes an HDF5 that opens and contains coords and a feature dataset whose row count differs, exercising the validator rather than the executor

### Requirement: Cohort-first-pass, per-file-recovery dispatch
The scheduler SHALL dispatch the first pass over a cohort as one invocation per input directory to amortize model load, and SHALL dispatch recovery retries per individual slide file. Per-slide outcome accounting SHALL be derived from the filesystem regardless of dispatch granularity.

#### Scenario: First pass then targeted retry
- **WHEN** a cohort directory is processed in one invocation and two slides are found invalid afterward
- **THEN** the scheduler re-dispatches only those two slides as per-file invocations, leaving the already-valid slides untouched

### Requirement: Worker does not classify failures
The worker SHALL report the raw outcome (exit code, stdout/stderr tails, timing, produced output paths) and SHALL NOT classify failures or decide recovery actions; classification is the recovery agent's responsibility.

#### Scenario: Raw outcome forwarded
- **WHEN** an invocation exits nonzero
- **THEN** the worker forwards the unclassified raw outcome for downstream validation and classification without labeling the failure itself
