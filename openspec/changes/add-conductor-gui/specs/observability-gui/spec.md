## ADDED Requirements

### Requirement: Read-only renderer over telemetry
The GUI SHALL be a read-only observability surface. It SHALL read the append-only telemetry
families (`jobs`, `slide_stage_outcomes`, `validation_results`, `agent_events`) and SHALL
NOT provide any control that mutates a run, submits a job, confirms a HITL action, or writes
back to the telemetry sink.

#### Scenario: No control affordance is offered
- **WHEN** the GUI is displayed for any run
- **THEN** it presents only observation panels (history, verdicts, trace, metrics) and exposes no button or input that submits a job, confirms an action, or edits telemetry

#### Scenario: GUI reads without hooking the orchestrator
- **WHEN** the GUI displays a run's state
- **THEN** it obtains that state by reading the append-only telemetry records, not by importing or calling into the running orchestrator process

### Requirement: No pixels, no clinical scores
The GUI SHALL render operational metadata only. It SHALL NOT render any slide pixel, tissue
mask, or heatmap image, and it SHALL NOT display any confidence, probability, or diagnostic
score. Verdicts SHALL be presented as the validator's structural pass/fail with a reason
code, never as a prediction with a likelihood.

#### Scenario: No image element is ever rendered
- **WHEN** any GUI panel renders for any run
- **THEN** no image element is produced by the app

#### Scenario: Verdicts carry no confidence score
- **WHEN** the per-slide verdict panel renders a slide's outcome
- **THEN** it shows the structural verdict and its reason code, and shows no confidence, probability, or diagnostic score

### Requirement: Renders over PHI-free records without importing the pipeline
The GUI SHALL import nothing from `atlas_patch` and SHALL depend only on the PHI-free
telemetry records. It SHALL display slide identifiers exactly as the telemetry persists them
(pseudonymized when the run gated them), never re-deriving a raw identifier.

#### Scenario: Independent of the ML pipeline
- **WHEN** the GUI module is imported
- **THEN** it pulls in no `atlas_patch` module and requires no GPU, model weight, or slide file to run

#### Scenario: Slide identity matches the persisted telemetry
- **WHEN** a run persisted pseudonymized slide stems
- **THEN** the GUI displays those same pseudonyms and never reconstructs the raw stem

### Requirement: Core observability panels
The GUI SHALL provide, over the telemetry families, at least: a run-history panel sourced
from `jobs`; a per-slide verdict panel sourced from `validation_results` and
`slide_stage_outcomes`; a decision-trace panel sourced from `agent_events`; and a
cohort-metrics panel with the run's valid/skipped/quarantined/blocked tallies.

#### Scenario: Panels populate from telemetry
- **WHEN** a completed run's telemetry is loaded
- **THEN** the history, verdict, trace, and metrics panels each render from their telemetry family with the run's recorded values

#### Scenario: Empty telemetry renders without error
- **WHEN** no runs have been recorded yet
- **THEN** the GUI renders an empty state and raises no exception
