# orchestration-run Specification

## Purpose
TBD - created by archiving change add-atlas-conductor. Update Purpose after archive.
## Requirements
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

### Requirement: Report surfaces the decision trace, not only outcomes
The report SHALL surface, per slide, the ordered decisions that produced the outcome — state reconciliation, dispatch, validation with reason code, and any recovery action — and not only the final verdict and cohort counts. The trace SHALL be sourced from the append-only telemetry records (`agent_events`, `slide_stage_outcomes`) and SHALL contain operational metadata only (no pixels, no PHI). The report SHALL be summary-first, exposing per-slide decision detail on demand (including under `--dry-run`), so a large cohort does not force full-trace output.

#### Scenario: Recovered slide shows its decision path
- **WHEN** a slide is dispatched, fails validation on a NaN, is recovered by a bounded retry, and then validates
- **THEN** the per-slide detail shows the ordered steps reconcile → dispatch → validate(`nan`) → recover(retry) → validate(valid), each carrying operational metadata only

#### Scenario: Dry run shows decisions without dispatch
- **WHEN** the orchestrator runs with `--dry-run`
- **THEN** the report shows the per-slide reconciliation decisions (`skip`/`run`/`reuse`/`blocked`) with reasons and dispatches no work

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

### Requirement: Deterministic core, no clinical reasoning
The orchestrator SHALL make only operational decisions (which CLI command to run, whether an HDF5 output is structurally valid, whether and how to retry) and SHALL NOT perform, embed, or delegate any clinical or diagnostic interpretation of slide content. No vision-language model or other probabilistic reasoner SHALL be placed on the plan/dispatch/validate/recover path. This keeps the layer out of Software-as-a-Medical-Device scope and preserves the structural-not-clinical invariant by construction. (The by-construction governance guardrails that build on this invariant — PHI-free write-gate, HITL, egress assertion, audit trail, Model Card — are phase 2, `add-conductor-governance`.)

#### Scenario: No diagnostic verdict is ever produced
- **WHEN** the orchestrator completes a run and emits its summary
- **THEN** the summary reports per-slide operational outcomes (present/valid/missing/invalid/blocked) and never a clinical finding, diagnosis, or interpretation of tissue

#### Scenario: The decision path contains no model inference
- **WHEN** any planning, dispatch, validation, or recovery decision is taken
- **THEN** the decision is a deterministic function of filesystem state, exit codes, and typed outcomes, with no model inference call on the path
