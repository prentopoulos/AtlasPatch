## 1. Lineage data model and hashing (D-LIN-2, D-LIN-3)

- [x] 1.1 Add `atlas_conductor/lineage/__init__.py` and a `records.py` defining the frozen `LineageRecord` dataclass (`job_id`, pseudonymized `slide_stem`, `input_sha256` tuple, `output_sha256`, `config_fingerprint`, `tool_version`, `recorded_at`) — scalars/strings only, no array-capable field.
- [x] 1.2 Implement `sha256_file(path)` streaming chunked hashing and `config_fingerprint(config)` (deterministic hash over patch_size, target_mag, step_size, sorted encoders, requested_output, idempotency key), with unit tests asserting stability and change-detection.
- [x] 1.3 Resolve the tool version via `importlib.metadata` for the `atlas-patch` distribution (not by importing `atlas_patch`); unit-test the fallback when metadata is absent.

## 2. Backend seam and default manifest backend (D-LIN-1, D-LIN-5, D-LIN-6)

- [x] 2.1 Define the `LineageBackend` ABC with `record(run: LineageInput) -> LineageResult`, and a `LineageInput` describing a finished run (output_dir, resolved input↔output artifact set, config, job_id).
- [x] 2.2 Implement `ManifestLineage` (stdlib only): resolve produced HDF5s from `output_dir`, hash inputs/outputs, build `LineageRecord`s, and append a JSON manifest at `<output_dir>/lineage/manifest.jsonl`.
- [x] 2.3 Route every slide identifier through `pseudonymize_stem` and every free-text field through `safe_harbor_findings` (fail closed), reusing `governance/phi.py`; unit-test that a raw-identifier stem is pseudonymized and a leaked identifier is rejected.
- [x] 2.4 Add the artifact-resolution helper that reads `output_dir` + run telemetry (the read-only report path) to map each output HDF5 to its input WSI(s) and pseudonym; record an output with an empty input-hash tuple rather than failing when an input is unresolvable.

## 3. Backend selection and run wiring (D-LIN-7)

- [x] 3.1 Add `make_lineage_backend(name)` in `run.py` (`manifest` default, `dvc` opt-in) mirroring `make_adapter`/`make_telemetry_sink`.
- [x] 3.2 Parse an optional `lineage:` block in `config.py` (`backend: manifest|dvc`, default off) with validation errors matching the existing `_parse_telemetry` style; unit-test parse + rejection of an unknown backend.
- [x] 3.3 Invoke lineage in `run_job` **after** the scheduler returns when the config enables it; assert via test that enabling it changes no plan/dispatch/validation/recovery/telemetry output (byte-identical run).

## 4. CLI subcommand

- [x] 4.1 Add `atlaspatch-conduct lineage <output-dir>` to `cli.py` with `--backend {manifest,dvc}` (default `manifest`), recording lineage over a finished run's outputs + telemetry; import no `dvc` at CLI module level.
- [x] 4.2 Test the subcommand records a manifest over a fake-adapter run and leaves the run's HDF5s and telemetry unmodified.

## 5. DVC backend, behind the extra (D-LIN-4)

- [ ] 5.1 Add `dvc>=<pinned>` to the `orchestrator` extra in `pyproject.toml` with a comment noting the verified version and the guarded-import rule; add nothing to core deps.
- [ ] 5.2 Implement `DvcLineage` in `atlas_conductor/lineage/dvc_backend.py`, importing/shelling to `dvc` only inside its methods: write a `dvc.yaml` stage (deps = input cohort + config, outs = output HDF5s) and `.dvc` pointers carrying the D-LIN-2 hashes, using pseudonymized relative identifiers; perform no `dvc push`.
- [ ] 5.3 Unit-test `DvcLineage` with the `dvc` invocation faked: assert a `dvc.yaml` stage + pointers are produced, that they carry the same hashes as the manifest backend, and that no raw stem/filename appears in any tracked path.

## 6. Guards, docs, and CI

- [ ] 6.1 Extend the existing import-guard test so importing core `atlas_conductor` and running the base `atlaspatch` CLI import neither `dvc` nor the DVC backend module.
- [ ] 6.2 Add an end-to-end test: a fake-adapter run with `lineage: {backend: manifest}` writes a manifest whose records content-address every produced output and reproduce identical hashes on re-record, and differ after an input's bytes change.
- [ ] 6.3 Document the lineage subcommand, the `lineage:` config block, and the no-pixel-egress guarantee in the README/conductor docs; run ruff + mypy + pytest green with `dvc` absent.
