## ADDED Requirements

### Requirement: Structural validity predicate over HDF5 outputs
The validator SHALL determine the structural validity of a slide's requested output by reading the documented HDF5 format only, checking that: the file opens; the `coords` dataset is present, 2-D with at least two columns, and non-empty; the required integer file attributes (`patch_size`, `patch_size_level0`, `target_magnification`) are present and match the job's requested geometry; and, for a `features` request, each requested `features/<encoder>` dataset is present, 2-D, has a row count equal to the coords row count, and contains no NaN values. The validator SHALL NOT import `atlas_patch` internals to perform these checks.

#### Scenario: Fully valid feature output
- **WHEN** an HDF5 opens, has non-empty coords, matching geometry attrs, and a `features/<encoder>` dataset with rows equal to coords and no NaNs
- **THEN** the validator returns a `valid` verdict for that slide

#### Scenario: Feature/coord row mismatch
- **WHEN** a `features/<encoder>` dataset has a different row count than `coords`
- **THEN** the validator returns an `invalid` verdict with a reason code identifying the row mismatch

#### Scenario: NaN-bearing features
- **WHEN** a `features/<encoder>` dataset contains any NaN value
- **THEN** the validator returns an `invalid` verdict with a reason code identifying the NaNs, even though AtlasPatch itself does not check for NaNs

#### Scenario: Unopenable or missing file
- **WHEN** the expected HDF5 is absent or fails to open
- **THEN** the validator returns an `invalid` verdict with a reason code distinguishing "missing" from "corrupt"

### Requirement: One predicate used at plan time and post-run
The validator's predicate SHALL be a pure function of filesystem state with no side effects, so the planner can call it before dispatch (to decide skip) and the orchestrator can call it after execution (to verify), yielding identical verdicts for identical on-disk state.

#### Scenario: Same on-disk state yields same verdict
- **WHEN** the predicate is evaluated for a slide before dispatch and again after a run that did not change that slide's file
- **THEN** both evaluations return the same verdict

### Requirement: Per-slide verdicts drive outcome, not CLI exit code
The validator's per-slide verdict SHALL be the authoritative determinant of whether a slide succeeded. A slide with a `valid` verdict SHALL be treated as succeeded even if its invocation shared a process with a failed slide, and a slide with an `invalid` verdict SHALL be treated as failed even if the invocation exited zero.

#### Scenario: Exit zero but structurally invalid
- **WHEN** an invocation exits zero but a target's output is structurally invalid
- **THEN** that target is recorded as failed based on the validator verdict, not as succeeded based on the exit code
