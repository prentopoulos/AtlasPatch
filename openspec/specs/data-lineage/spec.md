# data-lineage Specification

## Purpose
TBD - created by archiving change add-conductor-data-lineage. Update Purpose after archive.
## Requirements
### Requirement: Content-addressed lineage record per output artifact

The orchestrator SHALL be able to emit, for a completed run, one lineage record per output
HDF5 artifact that content-addresses the run: the SHA-256 of each input WSI that fed the
artifact, a config fingerprint (patch geometry, encoders, requested output, and the run's
idempotency key), the SHA-256 of the produced HDF5, the AtlasPatch tool version, and the
`job_id`. The record SHALL identify the slide by its pseudonymized stem so it correlates
with the run's existing telemetry, and SHALL contain no array, pixel, or embedding data —
only hashes, identifiers, and config scalars.

#### Scenario: A run's outputs are content-addressed into lineage records

- **WHEN** lineage is recorded over a completed run that produced HDF5 outputs for several slides
- **THEN** each output yields a record carrying the SHA-256 of its input(s), the SHA-256 of the output HDF5, the config fingerprint, the tool version, and the `job_id`, and the records collectively cover every produced artifact

#### Scenario: A record identifies the slide only by pseudonym

- **WHEN** a lineage record is written for a slide whose raw stem is itself an identifier
- **THEN** the record names the slide by its `slide_<hex>` pseudonym and nowhere carries the raw stem or WSI filename

### Requirement: Lineage detects changed inputs or config

Re-recording lineage after an input WSI or the job config has changed SHALL produce a record
whose hashes differ from the prior record for the same slide, so that a content or config
change is detectable from the lineage alone; re-recording an unchanged run SHALL reproduce
identical hashes.

#### Scenario: A changed input yields a different input hash

- **WHEN** an input WSI's bytes change and lineage is recorded again for the same slide
- **THEN** the new record's input SHA-256 differs from the prior record's, while an unchanged sibling slide's input hash is unchanged

#### Scenario: A changed geometry yields a different config fingerprint

- **WHEN** the job config's patch geometry changes and lineage is recorded again
- **THEN** the config fingerprint in the new records differs from the prior fingerprint

### Requirement: Pluggable lineage backend with a credential-free default

Lineage recording SHALL be performed through a single `LineageBackend` interface with at
least two implementations selectable without changing what is recorded: a default
manifest backend that uses only the Python standard library (no DVC, no network, no
credentials) and writes a JSON manifest, and an opt-in DVC backend that lives behind the
`orchestrator` extra. The default backend SHALL be the path exercised in CI. Importing the
core `atlas_conductor` package or running the core `atlaspatch` CLI SHALL NOT import `dvc`.

#### Scenario: Default backend records lineage with no DVC installed

- **WHEN** lineage is recorded with the default backend in an environment where `dvc` is not installed
- **THEN** a JSON lineage manifest is written and the operation succeeds without importing `dvc`

#### Scenario: DVC import is confined to its guarded backend

- **WHEN** the core `atlas_conductor` package is imported or the base `atlaspatch` CLI is run
- **THEN** `dvc` is not imported, and it is imported only when the DVC lineage backend is explicitly selected

### Requirement: DVC backend records lineage as version-controllable pointers

When the DVC backend is selected, the orchestrator SHALL write DVC pointer artifacts and a
`dvc.yaml` pipeline stage that declare the run reproducibly — its dependencies being the
input cohort and config and its outputs being the produced HDF5s — so that the lineage is
captured as content-addressed files a caller can commit to Git. The DVC backend SHALL record
the same content hashes and pseudonymized identifiers as the default backend and SHALL NOT
embed a raw WSI filename or HIPAA identifier in any tracked path or pipeline field.

#### Scenario: A DVC stage declares the run's deps and outs

- **WHEN** lineage is recorded with the DVC backend over a completed run
- **THEN** a `dvc.yaml` stage and DVC pointer files are produced that reference the run's inputs, config, and output HDF5s by content hash

#### Scenario: DVC-tracked paths carry no raw identifier

- **WHEN** the DVC backend records a slide whose raw stem is an identifier
- **THEN** no `.dvc` pointer, `dvc.yaml` field, or lock entry contains the raw stem or WSI filename

### Requirement: Lineage is PHI-free and moves no pixels

The lineage layer SHALL persist metadata only — content hashes, config scalars, tool
version, and pseudonymized identifiers — and SHALL NOT copy, track, or push any WSI pixels,
tissue masks, or embedding arrays to any DVC cache or remote. Free-text fields in a lineage
record SHALL pass the phase-2 Safe-Harbor gate, failing closed if an identifier shape leaks.
The lineage layer SHALL NOT push data to a DVC remote as part of recording.

#### Scenario: No pixels are copied or pushed

- **WHEN** lineage is recorded for a run with either backend
- **THEN** input pixels and output arrays remain only in their on-disk HDF5/WSI files, nothing is copied into a DVC remote, and only hashes stand in for the data

#### Scenario: A leaked identifier in a lineage field is rejected

- **WHEN** a lineage record would carry a HIPAA Safe-Harbor identifier shape in a free-text field
- **THEN** the write is rejected (fail closed) rather than persisting the identifier

### Requirement: Lineage recording is invocable and off by default

The orchestrator SHALL expose lineage recording both as an `atlaspatch-conduct lineage`
subcommand over a completed run's output directory and telemetry, and as an optional
`lineage:` job-config block that records automatically at the end of a run. Lineage
recording SHALL be off unless explicitly requested, and enabling it SHALL NOT change any
run's plan, dispatch, validation, recovery, or telemetry outputs. Reading a run to produce
lineage SHALL use the same read-only path as the report/GUI and SHALL NOT modify `atlas_patch`
or the run's outputs.

#### Scenario: The subcommand records lineage over a finished run

- **WHEN** `atlaspatch-conduct lineage` is invoked against a completed run's output directory
- **THEN** lineage records are written for that run's outputs and the run's HDF5s and telemetry are left unmodified

#### Scenario: Lineage off by default changes nothing

- **WHEN** a run executes without any `lineage:` config and without the subcommand
- **THEN** no lineage artifact is written and the run's outputs and telemetry are byte-identical to a run of the same config before this capability existed

#### Scenario: Config-driven lineage records at run end

- **WHEN** a job config includes a `lineage:` block enabling recording and the run completes
- **THEN** lineage records are emitted for the run's outputs without altering any plan, dispatch, validation, recovery, or telemetry result
