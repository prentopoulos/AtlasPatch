# AtlasPatch Orchestration Layer (`atlas_conductor`)

`atlas_conductor` runs the AtlasPatch pipeline reliably at cohort scale. It plans work,
dispatches it, validates the HDF5 outputs, recovers from failures, and records
metadata-only telemetry — **without modifying the ML pipeline**. It integrates with
AtlasPatch through exactly two documented surfaces: the CLI argv (to run work) and the
HDF5 output format at `<output>/patches/<stem>.h5` (to verify it). It imports no
`atlas_patch` internals.

## Install

The orchestrator's runtime dependency (PyYAML) ships in an optional extra; core AtlasPatch
install is unchanged.

```bash
pip install "atlas-patch[orchestrator]"
```

This installs the `atlaspatch-conduct` console command.

## Job config (YAML)

A run is described by a single YAML file:

```yaml
input_dir: /data/cohort        # directory of whole-slide images
output_dir: /data/out          # AtlasPatch output root (HDF5s land in <output_dir>/patches/)
requested_output: features     # 'coords' or 'features'
patch_size: 256
target_mag: 20
step_size: 256                 # optional
encoders:                      # required when requested_output is 'features'
  - resnet50
attempt_budget: 3              # optional; per-item recovery retry budget (default 3)
```

Keys may use hyphens or underscores (`patch-size` or `patch_size`). A config that omits a
required field, or requests an output outside the MVP set (`coords` → `segment-and-get-coords`,
`features` → `process`), is rejected before any work is dispatched.

## Run it

Against the **fake adapter** (no GPU, no real slides — writes real, canned HDF5s; useful for
trying the workflow or in CI):

```bash
atlaspatch-conduct run job.yaml            # defaults to --adapter fake
```

Against the **real adapter** (drives the AtlasPatch CLI as a subprocess):

```bash
atlaspatch-conduct run job.yaml --adapter real
```

Preview the plan without dispatching anything:

```bash
atlaspatch-conduct run job.yaml --dry-run
```

Control how much of the per-slide decision trace the report prints:

```bash
atlaspatch-conduct run job.yaml --trace all      # failures (default) | all | none
```

## Reading the report

The terminal report is summary-first: a per-slide outcome line plus cohort counts,
reflecting the **validator's per-slide verdicts**, never the CLI exit code.

```
============================================================
atlas_conductor run 1a2b3c4d5e6f
cohort=/data/cohort  output=features  geometry=ps256/mag20
------------------------------------------------------------
  slide_a                          valid
  slide_b                          quarantined  attempts-exhausted - ...
      planner:reconcile(missing) - segment=run embed=run
      worker:dispatch - run command=process attempt=1
      validator:verdict(nan-features) - quarantined
------------------------------------------------------------
  cohort=2  valid=1  skipped=0  quarantined=1  blocked=0
============================================================
```

Per-slide outcomes are one of: **valid**, **skipped** (already valid on disk), **quarantined**
(retries exhausted or still invalid after a forced rebuild), or **blocked** (geometry conflict,
inadmissible input, or an unsatisfiable precondition). Non-valid slides show their
**decision trace** — the ordered `reconcile → dispatch → validate(reason) → recover` steps,
sourced from the telemetry records and carrying operational metadata only.

## What the planner decides

- **Skip** a slide whose requested output is already present and structurally valid.
- **Reuse** existing coords when only features are missing (relies on AtlasPatch's own
  coord reuse), running only the embed stage.
- **Block** a slide whose existing HDF5 was produced with a different patch size or target
  magnification (rerun with `--force` or a different `output_dir`), and reject inadmissible
  cohorts up front (empty cohort, no WSI-extension files, unreadable/zero-byte inputs).

## Recovery

When a slide's output is invalid, the recovery agent classifies the failure into a bounded
taxonomy (resource-transient, precondition-block, input-data, structural-invalid, unknown)
from the execution stderr signature and the structural verdict, and proposes a bounded action
drawn only from AtlasPatch's own tuning knobs:

- **resource-transient** (e.g. CUDA-OOM) → retry with a smaller batch along a monotone ladder,
  then quarantine once the attempt budget is exhausted;
- **structural-invalid** (row mismatch / NaN) → rebuild once with `--force`, then quarantine;
- **precondition-block** (missing token / gated encoder) → block, and mark dependent stages
  `dependency-blocked` so they are never scheduled;
- **unknown** → block (never blindly retried), surfacing the raw stderr tail for triage.

## Telemetry

Every run appends metadata-only records — `jobs`, `slide_stage_outcomes`, `validation_results`,
`agent_events` — to a local sink (`<output_dir>/telemetry/*.jsonl` by default; override with
`--telemetry-dir`). The record types hold only scalars, enums, timestamps, and identifiers —
**no image, mask, or embedding field exists** — so pixels and embeddings never leave the
AtlasPatch HDF5. Each recovery attempt is logged with its `(signature, classification, action,
resolved)` tuple, so the telemetry doubles as a labeled dataset of recovery outcomes.
