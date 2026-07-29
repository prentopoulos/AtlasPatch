## Context

Phases 1–4 built the operational core (planner / worker / validator / recovery over the
AtlasPatch CLI + HDF5), a PHI-free write-gated telemetry sink (families `jobs`,
`slide_stage_outcomes`, `validation_results`, `agent_events`, `message_flow`), a read-only
Streamlit GUI, and an opt-in A2A transport + BigQuery backend. The telemetry answers *what
the run decided*, but nothing content-addresses **which input bytes plus which config
produced which output HDF5**, and nothing is committed to a version-controlled store an
auditor can replay. The `run-telemetry`/governance layers deliberately keep only metadata;
the raw data lives in the AtlasPatch HDF5 at `<output_dir>/patches/<stem>.h5` and in the
input WSIs.

This phase adds a **data-lineage** layer — a fifth, additive artifact that content-addresses
each run's inputs and outputs — reusing three seams the repo already established:

- The **pluggable-backend-behind-one-interface** pattern (real/fake adapter, jsonl/bigquery
  sink, in-process/a2a transport): a default credential-free implementation is the CI target;
  a heavy opt-in implementation lives behind the `orchestrator` extra with a guarded import.
- The **phase-2 PHI gate** (`governance/phi.py`): `pseudonymize_stem` + `safe_harbor_findings`,
  reused verbatim so the manifest inherits the same by-construction guarantee.
- The **read-only "observe a finished run" path** the GUI and `export-report` already use:
  read `output_dir` + telemetry, write a sibling artifact, touch nothing upstream.

Hard constraints from PROJECT.md carry in unchanged: `atlas_patch/` untouched; metadata-only
and PHI-free; operational-not-clinical; heavy deps (`dvc`) behind `atlas-patch[orchestrator]`
so `pip install atlas-patch` and the base `atlaspatch` CLI stay unaffected and the default
path is green in CI with no cloud, no DVC, and no credentials.

## Goals / Non-Goals

**Goals:**
- A `LineageBackend` seam with `ManifestLineage` (default, stdlib `hashlib` + JSON) and
  `DvcLineage` (opt-in, `dvc` extra), selected the way real/fake and jsonl/bigquery already
  are, recording the same records regardless of backend.
- One content-addressed lineage record per output HDF5: input SHA-256(s), config fingerprint
  (geometry + encoders + requested output + idempotency key), output SHA-256, tool version,
  `job_id`, keyed on the pseudonymized stem.
- Reproducibility check: identical inputs + config reproduce identical hashes; a changed
  input or geometry produces a detectably different record.
- An `atlaspatch-conduct lineage <output-dir>` subcommand and an optional `lineage:` config
  block, both **off by default**, that add no behavior to a run when unused.
- CI green on the default backend against the fake adapter with `dvc` absent; the DVC backend
  unit-tested behind its guard with the CLI faked.

**Non-Goals:**
- Pushing any pixels, masks, or embeddings into a DVC cache or remote — this layer moves
  **hashes**, never data (D-LIN-5). A shared DVC remote and `dvc push` are explicitly out of
  scope.
- Changing any run's plan, dispatch, validation, recovery, or the five telemetry families'
  shapes.
- Auto-committing to Git, opening branches, or managing a Git remote — the DVC backend
  produces committable files; the human/CI decides when to commit.
- The learned recovery classifier (phase 6) or the compliance dossier (phase 7); this phase
  only produces the lineage those consume.
- Touching `atlas_patch/` or making `dvc` a core dependency.

## Decisions

### D-LIN-1 — A `LineageBackend` seam, mirroring the established backend pattern

Add `atlas_conductor/lineage/` with a `LineageBackend` abstract base exposing a single
`record(run: LineageInput) -> LineageResult` method, and two implementations:
`ManifestLineage` (default) and `DvcLineage` (opt-in). `run.py`/`cli.py` select the backend
by name exactly as `make_adapter`/`make_telemetry_sink` do today. Rationale: the repo has
proved this pattern three times; a fourth instance keeps DVC a swappable backend, not a
rewrite, and keeps the default path free of the heavy dependency. *Alternative rejected:*
making DVC the only backend — it would drag `dvc` onto the core install path and make CI
depend on a DVC binary, violating the credential/dep-free-default constraint.

### D-LIN-2 — A `LineageRecord` is hashes + config identity, nothing else

The record is a frozen dataclass of scalars/strings: `job_id`, `slide_stem` (pseudonym),
`input_sha256` (tuple, one per input WSI feeding the slide), `output_sha256`,
`config_fingerprint`, `tool_version`, `recorded_at`. By type it cannot hold an array — the
same by-construction argument as the telemetry records (design D9). The
`config_fingerprint` is a short deterministic hash over `(patch_size, target_mag, step_size,
sorted(encoders), requested_output, idempotency_key)` so a config edit that changes geometry
changes the fingerprint (aligned with `make_idempotency_key`). *Alternative rejected:*
storing the full config blob — larger, and risks folding a raw input path into the record.

### D-LIN-3 — Hash inputs and outputs by streaming bytes; never open the HDF5 semantically

Both backends compute SHA-256 by streaming file bytes in fixed chunks (`hashlib`), treating
WSIs and HDF5s as opaque blobs. The layer never parses slide content and never interprets
the HDF5 beyond its bytes — preserving the operational-not-clinical invariant and avoiding
any `atlas_patch` import. The set of input WSIs and output HDF5 for a slide is resolved from
the run's telemetry + `output_dir` (the pseudonym↔stem mapping is available within the run),
the same read-only source the report uses. *Alternative rejected:* hashing datasets inside
the HDF5 — needs `h5py` semantics and couples lineage to the file's internal schema.

### D-LIN-4 — `DvcLineage` writes committable pointers, invokes `dvc` only through its module

`DvcLineage` lives in `atlas_conductor/lineage/dvc_backend.py` and imports `dvc` (or shells
to the `dvc` CLI) only inside its methods, never at module top level touched by the core
graph — enforced by the existing CI import-guard test that already covers streamlit/adk/
bigquery. It writes a `dvc.yaml` stage (deps = input cohort + config; outs = output HDF5s)
and `.dvc` pointer files carrying the D-LIN-2 hashes, using **pseudonymized, relative**
output identifiers so no raw filename lands in a tracked path (D-LIN-6). It does **not**
run `dvc push`. Rationale: the phase-5 value is a *version-controllable* provenance trail —
`dvc.yaml` + `.dvc` files under Git are exactly that — without this layer becoming a data
mover. *Alternative rejected:* `dvc add` on the raw input WSIs — that would content-track
pixel files into the DVC cache (pixel movement) and put raw filenames in `.dvc` paths.

### D-LIN-5 — Hashes stand in for pixels; nothing is copied or pushed

The manifest and the DVC pointers record **content hashes** of inputs, never the input bytes
themselves. No code path in this layer copies a WSI/HDF5 into a DVC cache, and no `dvc push`
/remote call exists. This is what keeps the no-pixel-egress guarantee (governance
`phi-safe-telemetry`: "No PHI or pixel data can egress the layer") true for lineage: an
auditor can prove "these exact input bytes produced this exact output" from hashes alone,
with the pixels never leaving the operator's disk.

### D-LIN-6 — Reuse the phase-2 gate for every free-text/identifier field

Slide identity in every lineage artifact is the `pseudonymize_stem(stem, job_id)` token, and
any free-text field is run through `safe_harbor_findings` and **fails closed** on a hit —
the same `PhiSafeSink` discipline, reused rather than reimplemented. This makes the PHI-free
and no-raw-identifier scenarios (spec) hold by construction for both backends, including the
DVC-tracked paths.

### D-LIN-7 — Off by default, additive to the run façade

Lineage is invoked two ways, both defaulting to off: the `atlaspatch-conduct lineage
<output-dir>` subcommand (post-hoc, over a finished run) and an optional `lineage:` block in
the job config (`backend: manifest|dvc`, default `manifest`) that `run_job` invokes **after**
the scheduler returns, reading the just-written telemetry + outputs. Because it runs after
dispatch/validation/recovery and writes only a new sibling artifact, enabling it cannot
change any plan/dispatch/validation/recovery/telemetry result — the "off by default changes
nothing" and "config-driven records at run end" scenarios. *Alternative rejected:* emitting
lineage inline during dispatch — it would entangle lineage with the scheduler governor and
risk changing run behavior.

## Risks / Trade-offs

- **Hashing large WSIs adds wall-clock time** → Streaming chunked SHA-256 is I/O-bound and
  runs once per artifact, after the (far heavier) run; it is opt-in, so the default fast path
  is unaffected. Cohort-scale cost is linear in bytes read, not in slides opened.
- **A `.dvc`/`dvc.yaml` path could leak a raw filename** → All tracked identifiers are
  pseudonymized and relative (D-LIN-6); a CI scenario asserts no raw stem appears in any
  DVC-tracked path, and the Safe-Harbor gate is the backstop.
- **`dvc` version/CLI drift** → The DVC backend is behind the extra and import-guarded; its
  tests fake the `dvc` invocation so CI never depends on a real `dvc` binary, matching how the
  A2A/BigQuery paths are tested. Pin a minimum `dvc` in the extra and note the verified version.
- **Telemetry may not name every input↔output pair** → Resolve the artifact set from
  `output_dir` (the produced HDF5s are ground truth) and map back to inputs via the run's
  config/pseudonym mapping; if an output has no resolvable input, record it with an empty
  input-hash tuple rather than failing the whole manifest, and surface the gap.

## Migration Plan

Additive and reversible: new `atlas_conductor/lineage/` package, one new CLI subcommand, an
optional config block, and one post-run hook in `run_job`. `dvc` is added only to the
`orchestrator` extra. No data migration, no change to existing artifacts. Rollback = do not
invoke the subcommand / omit the `lineage:` block (the default), or remove the package;
nothing else depends on it yet (phases 6–7 will).

## Open Questions

- **Manifest location and filename** — default to `<output_dir>/lineage/manifest.jsonl`
  (sibling to `telemetry/`) unless a reviewer prefers a single `lineage.json` per run.
- **Tool version source** — read `atlas_patch.__version__` if importable without pulling ML
  deps, else record the installed `atlas-patch` distribution version via `importlib.metadata`
  (preferred, avoids importing `atlas_patch`). Resolve during implementation.
- **Whether `dvc.yaml` should be one stage per run or one per slide** — leaning one stage per
  run (deps = cohort + config, outs = all HDF5s) for a readable pipeline; confirm against a
  real `dvc repro` during the DVC-backend task.
