## ADDED Requirements

### Requirement: Job config intake
The orchestrator SHALL accept a single YAML job config describing the cohort input directory, the requested output (`coords` or `features`), the patch geometry (`patch-size`, `target-mag`, optional `step-size`), and the encoder(s) for feature output. The orchestrator SHALL reject a config that is missing a required field or that requests an output the MVP does not support, with an actionable error, before any work is dispatched.

#### Scenario: Valid features job config
- **WHEN** a YAML config names an existing cohort directory, `requested_output: features`, a patch geometry, and one supported patch encoder
- **THEN** the orchestrator accepts the config and produces a plan without dispatching any execution

#### Scenario: Missing required field
- **WHEN** a YAML config omits `patch-size`
- **THEN** the orchestrator exits with a nonzero code and a message naming the missing field, and dispatches no work

#### Scenario: Unsupported requested output
- **WHEN** a YAML config requests an output that maps to a command outside the MVP set (`segment-and-get-coords`, `process`)
- **THEN** the orchestrator rejects the config with a message stating which outputs are supported

### Requirement: Terminal summary report
On completion the orchestrator SHALL emit a terminal summary report that states, per slide, the final stage outcome (valid, quarantined, or blocked) and the reason for any non-valid outcome, plus cohort-level counts. The report SHALL reflect the validator's per-slide verdicts, not the AtlasPatch CLI exit code.

#### Scenario: Mixed cohort outcome
- **WHEN** a run finishes with some slides valid, one quarantined after exhausting retries, and one blocked on a precondition
- **THEN** the report lists each slide with its outcome and reason and shows counts that sum to the cohort size

### Requirement: Upstream pipeline is never modified
The orchestrator SHALL integrate with AtlasPatch only by invoking its documented CLI commands and by reading its documented HDF5 output format. The orchestrator SHALL NOT import `atlas_patch` internal modules and SHALL NOT alter SAM2 segmentation, coordinate generation, feature extraction, the HDF5 format, or existing CLI behavior.

#### Scenario: Integration is CLI and file format only
- **WHEN** the orchestrator needs to run work or determine an outcome
- **THEN** it does so by constructing CLI argv and by reading `<output>/patches/<stem>.h5`, with no import of `atlas_patch` internals

### Requirement: Validation is structural, never clinical
The orchestrator SHALL restrict all validation to structural correctness of AtlasPatch outputs and SHALL make no medical or clinical claim about any slide.

#### Scenario: No clinical judgement
- **WHEN** an HDF5 output is validated
- **THEN** the verdict concerns only structural properties (file opens, datasets present, row alignment, absence of NaNs) and never the biological or diagnostic content of the slide
