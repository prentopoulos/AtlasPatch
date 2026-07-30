## MODIFIED Requirements

### Requirement: Read-only renderer over telemetry
The GUI SHALL be a read-only observability surface rendering the frozen `gui-snapshot` payload.
It SHALL obtain a run's state from a point-in-time snapshot (the versioned payload assembled from
the append-only telemetry families `jobs`, `slide_stage_outcomes`, `validation_results`,
`agent_events`, `message_flow`), and SHALL NOT provide any control that mutates a run, submits a
job, confirms a HITL action, or writes back to any telemetry sink or snapshot.

#### Scenario: No control affordance is offered
- **WHEN** the GUI is displayed for any run
- **THEN** it presents only observation panels (history, verdicts, trace, metrics, choreography) and exposes no button or input that submits a job, confirms an action, or edits telemetry or the snapshot

#### Scenario: GUI reads without hooking the orchestrator
- **WHEN** the GUI displays a run's state
- **THEN** it obtains that state by reading the snapshot payload, not by importing or calling into the running orchestrator process or reading a live telemetry sink

### Requirement: No pixels, no clinical scores
The GUI SHALL render operational metadata only. It SHALL NOT render any slide pixel, tissue
mask, or heatmap image, and it SHALL NOT display any confidence, probability, or diagnostic
score. Verdicts SHALL be presented as the validator's structural pass/fail with a reason code,
never as a prediction with a likelihood.

#### Scenario: No slide image is ever rendered
- **WHEN** any GUI panel renders for any run
- **THEN** no slide pixel, tissue mask, or heatmap image is rendered by the app (chrome iconography such as SVG UI glyphs is not slide imagery and is not restricted)

#### Scenario: Verdicts carry no confidence score
- **WHEN** the per-slide verdict panel renders a slide's outcome
- **THEN** it shows the structural verdict and its reason code, and shows no confidence, probability, or diagnostic score

### Requirement: Renders over PHI-free records without importing the pipeline
The GUI SHALL import nothing from `atlas_patch` and SHALL depend only on the PHI-free snapshot
payload. As a static client it SHALL require no Python runtime to view. It SHALL display slide
identifiers exactly as the snapshot persists them (pseudonymized when the run gated them), never
re-deriving a raw identifier.

#### Scenario: Independent of the ML pipeline
- **WHEN** the GUI is viewed
- **THEN** it pulls in no `atlas_patch` module and requires no Python runtime, GPU, model weight, or slide file to run

#### Scenario: Slide identity matches the persisted snapshot
- **WHEN** a run persisted pseudonymized slide stems
- **THEN** the GUI displays those same pseudonyms and never reconstructs the raw stem

### Requirement: Core observability panels
The GUI SHALL provide, over the snapshot payload, at least: a run-history panel sourced from the
per-run job rows; a per-slide verdict panel sourced from the run's `slides` (structural outcome,
reason code, and detail); a decision-trace panel sourced from each slide's `trace`; a
cohort-metrics panel with the run's valid/skipped/quarantined/blocked tallies; and an
agent-choreography panel presenting the derived Level-1 component-state and Level-2 message-flow.
The per-slide verdict panel SHALL be sortable and the decision trace SHALL render as a tree.

#### Scenario: Panels populate from the snapshot
- **WHEN** a snapshot with a completed run is loaded
- **THEN** the history, verdict, trace, metrics, and choreography panels each render from their section of the payload with the run's recorded values

#### Scenario: Empty snapshot renders without error
- **WHEN** a snapshot with an empty set of runs is loaded
- **THEN** the GUI renders an empty state and raises no error

## ADDED Requirements

### Requirement: Pins the snapshot schema version
The GUI SHALL pin the `gui-snapshot` `SNAPSHOT_SCHEMA_VERSION` it was built against and SHALL
compare it to a loaded snapshot's `schema_version`. On a mismatch it SHALL present an explicit
incompatibility state rather than mis-rendering an unrecognized shape.

#### Scenario: Matching schema version renders normally
- **WHEN** a snapshot whose `schema_version` equals the pinned version is loaded
- **THEN** the GUI renders its panels normally

#### Scenario: Mismatched schema version shows an incompatibility state
- **WHEN** a snapshot whose `schema_version` differs from the pinned version is loaded
- **THEN** the GUI shows an explicit version-incompatibility message and does not attempt to render the run panels

### Requirement: Loads a point-in-time snapshot with a bundled demo and a file loader
The GUI SHALL render a committed demo snapshot on first load with no operator input, and SHALL
let the operator load a real exported `snapshot.json` via a file picker or drag-and-drop,
replacing the view with the loaded run set. It SHALL NOT fetch from any server or poll for
updates — it is a static, point-in-time renderer.

#### Scenario: Default demo renders with no input
- **WHEN** the GUI is opened with no snapshot supplied
- **THEN** it renders the committed demo snapshot so the panels are populated out of the box

#### Scenario: Loading a snapshot file replaces the view
- **WHEN** the operator loads an exported `snapshot.json` via the file picker or drag-and-drop
- **THEN** the GUI re-renders its panels from the loaded snapshot's runs

#### Scenario: A malformed snapshot is rejected without crashing
- **WHEN** the operator loads a file that is not a well-formed snapshot payload
- **THEN** the GUI shows an error message and leaves the current view intact, raising no unhandled error

### Requirement: Ships as a static, Node-free-installable bundle
The GUI SHALL be distributed as a prebuilt static bundle carried in the Python package, so that
`pip install` requires neither Node nor a build step and the installed package can serve the GUI
without compiling it.

#### Scenario: Installed package carries the prebuilt bundle
- **WHEN** the Python package is installed
- **THEN** the prebuilt GUI bundle is present in the installed package and no Node toolchain or build step was required to install it

#### Scenario: Viewing the GUI requires no build
- **WHEN** an operator opens the shipped GUI bundle
- **THEN** it renders from the prebuilt static assets without a compile or bundling step at view time
