## 1. Snapshot assembly module

- [x] 1.1 Create `atlas_conductor/gui/snapshot.py` with a `SNAPSHOT_SCHEMA_VERSION` integer constant and a module docstring stating the D18 invariants the payload carries (PHI-free, no pixels, no scores) and that it imports no `streamlit`/`atlas_patch` (D-SNAP-1, D-SNAP-2, D-SNAP-5).
- [x] 1.2 Implement `run_snapshot(view: RunView) -> dict` serializing one run: job/history row, per-slide verdicts (structural outcome + reason_code + detail + trace), and cohort metrics (cohort_size + valid/skipped/quarantined/blocked counts) — reusing the existing `RunView`/`SlideView` shape (gui-snapshot: single snapshot, structural verdicts, cohort metrics).
- [x] 1.3 Extend `run_snapshot` to serialize the derived state per run: `choreography_state(view.events)` (active/lit/now-processing) and `message_flow_state(view.message_flow)` (edges + latest + has_flow) as JSON-safe dicts (gui-snapshot: derived choreography and message-flow state).
- [x] 1.4 Implement `assemble_snapshot(reader_or_dir) -> dict` returning `{"schema_version": SNAPSHOT_SCHEMA_VERSION, "runs": [run_snapshot(v) for v in build_run_views(reader)]}`, accepting either a `TelemetryReader` or a telemetry directory path; empty telemetry yields the versioned payload with an empty `runs` list (gui-snapshot: versioned snapshot, empty telemetry).
- [x] 1.5 (Resolve open question) Include a top-level `agents` roster from `choreography.AGENTS` so a renderer need not hardcode agent order; if omitted, note the decision in the module docstring.

## 2. Unify the JSON export onto the snapshot

- [x] 2.1 Re-point `export_json` in `atlas_conductor/gui/export.py` to emit `assemble_snapshot(...)` (versioned snapshot) instead of the partial `{"runs": [run_view_to_dict(...)]}`; keep `export_html` assembling from `build_run_views` unchanged (report-export: JSON sibling is the versioned snapshot; D-SNAP-3).
- [x] 2.2 Verify `export_report(telemetry_dir, fmt="json")` returns the versioned snapshot and `fmt="html"` is unchanged; remove `run_view_to_dict` only if it is no longer referenced, otherwise leave it for the HTML path.

## 3. Tests (pytest, existing `app` CI job)

- [x] 3.1 Round-trip test: write in-memory-sink records to JSONL, read via `TelemetryReader`, assemble a snapshot, and assert per-slide verdicts, reason codes, cohort counts, trace, and derived choreography/message-flow state match the recorded values (gui-snapshot: round-trip fidelity).
- [x] 3.2 Invariant test — no scores/pixels: assert the fully serialized snapshot JSON contains no confidence/probability/diagnostic score token and no image/mask/heatmap/embedding key, for a populated run (gui-snapshot: structural verdicts, no image/embedding; D-SNAP-4).
- [x] 3.3 PHI-free test: assemble a snapshot from a gated-run fixture and assert only the persisted pseudonymized stems appear and no raw identifier is present (gui-snapshot: PHI-free slide identity).
- [x] 3.4 Derived-state edge cases: a run with no `agent_events` yields idle choreography with no now-processing; a run with no `message_flow` yields `has_flow=false` and no fabricated edges (gui-snapshot: choreography reflects latest activity, message-flow degrades cleanly).
- [x] 3.5 Empty + versioning test: empty telemetry assembles to `{schema_version, runs: []}` without error, and a shape test pins the top-level keys so an unversioned breaking change fails CI (gui-snapshot: empty telemetry; D-SNAP-2).
- [x] 3.6 Export-agreement test: for the same run, assert the JSON snapshot and the HTML sibling report identical per-slide verdicts, reason codes, and cohort counts (report-export: HTML and JSON siblings agree; export and GUI agree).
- [x] 3.7 Import-guard: assert importing `atlas_conductor.gui.snapshot` pulls in no `streamlit` and no `atlas_patch` module (D-SNAP-5).

## 4. Docs and validation

- [x] 4.1 Update the README export note and the `export-report` CLI help to describe the versioned snapshot as the single machine-readable observability payload (JSON now carries schema version + derived state); note the JSON shape change.
- [x] 4.2 Run `openspec validate add-gui-snapshot-contract` and the `app` CI checks (ruff, mypy per local pre-commit, pytest) green; flip `PROJECT.md` phase 8 status per the `next-phase` workflow at implement/archive time.
