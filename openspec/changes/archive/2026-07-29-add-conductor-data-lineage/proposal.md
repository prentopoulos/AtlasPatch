## Why

The orchestrator's telemetry records *what the run decided* (families `jobs`,
`slide_stage_outcomes`, `validation_results`, `agent_events`, `message_flow`), but nothing
content-addresses **which exact input bytes plus which config produced which output HDF5**,
and nothing is committed to a version-controlled store an auditor can walk. Reproducing or
proving the provenance of a cohort result today means trusting filenames and timestamps.
The phase-7 compliance dossier (EU AI Act / ISO 42001) will need exactly this lineage, and
it is far cheaper to capture as an additive layer now than to reconstruct after the fact.

## What Changes

- Add a **`data-lineage`** capability: after a run, emit a **content-addressed lineage
  manifest** — one record per output artifact tying together the SHA-256 of each input WSI,
  a config fingerprint (geometry, encoders, requested output, idempotency key), the SHA-256
  of the produced HDF5, the AtlasPatch tool version, and the `job_id` — keyed on the
  **pseudonymized** slide stem so it correlates with the existing telemetry.
- Introduce a `LineageBackend` interface with two implementations behind it, mirroring the
  established real/fake, jsonl/bigquery, in-process/a2a seam pattern:
  - **`ManifestLineage`** (default): pure-stdlib `hashlib` + JSON manifest, no DVC, no
    credentials, no network — the green-in-CI path.
  - **`DvcLineage`** (opt-in, `orchestrator` extra): writes DVC pointer files and a
    `dvc.yaml` stage declaring the run as a reproducible pipeline (deps = inputs + config,
    outs = output HDF5s) so **Git history becomes the lineage record**.
- Add an `atlaspatch-conduct lineage <output-dir>` CLI subcommand that records lineage over
  a completed run's outputs + telemetry (the same read-only, PHI-free path the GUI and
  `export-report` use), and an optional `lineage:` job-config block to record automatically
  at run end. Both default to off / manifest-only.
- Route the manifest through the phase-2 pseudonymization + Safe-Harbor gate so raw WSI
  filenames and HIPAA identifiers never land in the manifest or in any `.dvc`/Git-tracked
  path — content **hashes** stand in for input pixels, so no pixels or embeddings are ever
  copied, tracked, or pushed to a remote.

## Capabilities

### New Capabilities
- `data-lineage`: content-addressed, PHI-free lineage records over each run's inputs and
  outputs; a `LineageBackend` seam with a default credential-free manifest backend and an
  opt-in DVC/Git backend; the `lineage` CLI subcommand and optional config block; and the
  no-pixel-egress guarantee (hashes only, no data pushed to a DVC remote by this layer).

### Modified Capabilities
<!-- None. Lineage reads the existing output HDF5s + telemetry after the fact and writes a
     new artifact; it changes no existing requirement. The optional `lineage:` config block
     and the CLI subcommand are owned by the new data-lineage spec, not by orchestration-run. -->

## Impact

- **Code (additive, new modules only):** `atlas_conductor/lineage/` (backend interface,
  `ManifestLineage`, guarded `DvcLineage`), a new `lineage` command in
  `atlas_conductor/cli.py`, an optional `lineage:` parse path in `atlas_conductor/config.py`,
  and a wiring hook in `atlas_conductor/run.py`. No change to the four telemetry families,
  the scheduler governor, or the four record shapes.
- **Dependencies:** `dvc` added to the `orchestrator` extra only, imported solely inside the
  guarded `DvcLineage` module (enforced by the existing CI import-guard test), so
  `pip install atlas-patch` and the core `atlaspatch` CLI stay unchanged and cloud-free.
- **Constraints honored:** `atlas_patch/` untouched (lineage reads the documented HDF5s and
  invokes nothing new upstream); manifest is metadata-only + PHI-free by reusing the phase-2
  gate; operational-not-clinical (hashes and config identity, no slide interpretation).
- **CI:** default `ManifestLineage` path is exercised against the fake adapter with no DVC
  installed; the `DvcLineage` path is unit-tested behind its guard.
