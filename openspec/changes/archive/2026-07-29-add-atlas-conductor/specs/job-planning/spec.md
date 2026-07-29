## ADDED Requirements

### Requirement: Plan expressed in logical stages
The planner SHALL express the plan as a DAG of logical stages (`segment`, `embed`) with dependency edges, and SHALL map stages onto AtlasPatch CLI commands via a stage-to-command mapping (`segment-and-get-coords` covers `{segment}`; `process` covers `{segment, embed}`). The planner SHALL NOT express the plan as a flat list of CLI commands.

#### Scenario: Features job produces a two-stage plan
- **WHEN** the requested output is `features` for a cohort
- **THEN** each slide's plan contains a `segment` stage and an `embed` stage with `embed` depending on `segment`, and the dispatch mapping resolves both to a single `process` invocation

#### Scenario: Coords job produces a single-stage plan
- **WHEN** the requested output is `coords`
- **THEN** each slide's plan contains only a `segment` stage mapped to `segment-and-get-coords`

### Requirement: Skip already-valid work
Before dispatch, the planner SHALL evaluate the structural-validity predicate for each slide's requested output and SHALL mark a slide `skip` when the requested output already exists and is structurally valid. Skip-if-valid SHALL use the same predicate as post-run validation.

#### Scenario: Valid feature output is skipped
- **WHEN** a slide's canonical HDF5 already contains coords and the requested `features/<encoder>` with rows aligned to coords and no NaNs
- **THEN** the planner marks that slide `skip` and it is not dispatched

#### Scenario: Coords present but features missing triggers reuse
- **WHEN** the requested output is `features`, coords exist and are valid, but the requested `features/<encoder>` dataset is absent
- **THEN** the planner marks the slide to run, relying on AtlasPatch's own coord reuse rather than recomputing segmentation

### Requirement: Branch on requested output
The planner SHALL choose the command and the meaning of "valid" from the requested output: a `coords` request is satisfied by valid coords alone; a `features` request additionally requires the aligned, NaN-free feature dataset for each requested encoder.

#### Scenario: Same slide, different requested output
- **WHEN** two jobs target the same slide, one requesting `coords` and one requesting `features`
- **THEN** the coords job may mark the slide `skip` while the features job marks the same slide to run, because validity is evaluated against the requested output

### Requirement: Block on geometry conflict
The planner SHALL detect, at plan time, when a slide's existing canonical HDF5 was produced with a `patch_size` or `target_magnification` that differs from the job's requested geometry, and SHALL mark that slide `blocked` with an actionable message rather than dispatching a run that AtlasPatch would reject.

#### Scenario: Existing HDF5 has incompatible patch size
- **WHEN** a slide already has an HDF5 at `patch_size=256` and the job requests `patch-size 512`
- **THEN** the planner marks the slide `blocked` with a message stating the conflict and the need for `--force` or a different output location, and does not dispatch it

### Requirement: Reject inadmissible input at plan time
Before dispatch, the planner SHALL reject a cohort whose input cannot be processed and SHALL mark it `blocked` with a reason code, rather than dispatching and inheriting a silent per-slide failure. Admissibility SHALL be a shallow check — cohort non-empty, at least one file matching a WSI extension allowlist, and each candidate file readable and non-zero size — and SHALL NOT decode slide contents; deep slide validation remains AtlasPatch's responsibility. Reason codes SHALL distinguish `empty-cohort`, `no-wsi-files`, and `unreadable-input`.

#### Scenario: Cohort directory contains no WSI files
- **WHEN** the cohort directory exists but contains no file matching the WSI extension allowlist
- **THEN** the planner blocks the cohort with reason code `no-wsi-files` and dispatches no work

#### Scenario: Empty cohort directory
- **WHEN** the cohort directory is empty
- **THEN** the planner blocks the cohort with reason code `empty-cohort` and dispatches no work

#### Scenario: Unreadable or zero-byte input
- **WHEN** a candidate WSI file is unreadable or zero bytes
- **THEN** the planner marks that input `blocked` with reason code `unreadable-input` before dispatch, and admissibility performs no slide decode
