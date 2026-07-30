## Context

Phase 3 (`add-conductor-gui`, design D18) shipped the read-only observability surface as three
cooperating pieces in `atlas_conductor/gui/`:

- `reader.py` — a read-only `TelemetryReader` over the append-only JSONL families (`jobs`,
  `slide_stage_outcomes`, `validation_results`, `agent_events`, `message_flow`).
- `model.py` — `build_run_views(reader)` assembles one `RunView` per job: the job row, the
  per-slide `SlideView` verdicts (structural outcome + reason code + detail + trace), the
  ordered `agent_events`, and the ordered `message_flow` rows.
- `choreography.py` / `messageflow.py` — derive Level-1 component-state and Level-2 message-flow
  state from those event/flow rows *at render time*.

Two renderers consume this today: the Streamlit `app.py`, and `export.py`, whose JSON path
emits a partial `{"runs": [run_view_to_dict(v)]}` that includes verdicts and trace but **not**
the derived choreography/message-flow state, and carries **no** schema version. Phase 9 will
add a React SPA renderer; it needs one complete, versioned, JSON-safe payload — not two partial
shapes and two render-time derivations. This phase freezes that payload. It is deliberately
Python-only and additive: no `streamlit`, no `atlas_patch`, no Node, no new dependency, and
`app.py` is untouched.

## Goals / Non-Goals

**Goals:**
- One `assemble_snapshot(reader | telemetry_dir) -> dict` in the GUI package producing a
  JSON-safe, schema-versioned payload with, per run: history/job row, per-slide verdicts,
  decision trace, cohort metrics, and the **derived** Level-1 choreography + Level-2
  message-flow state (moved from render-time into the payload).
- A `SNAPSHOT_SCHEMA_VERSION` constant that phase 9's renderer pins.
- Re-point `export_report(..., fmt="json")` at the snapshot so the JSON export *is* the
  contract; the HTML sibling keeps rendering the same assembled data.
- Round-trip and invariant tests in the existing `app` CI job (pytest only).

**Non-Goals:**
- Any renderer change. `app.py` stays as-is; no React this phase.
- Any telemetry schema change or new record family. The snapshot is *derived* from existing
  records, exactly as the current render-time helpers are (D-GUI-4).
- A live/streaming payload. The snapshot is a point-in-time serialization of a telemetry
  directory, matching today's refresh-to-update behavior.
- Rendering pixels, masks, heatmaps, or any confidence/diagnostic score — forbidden in the
  payload as in the GUI.

## Decisions

### D-SNAP-1 — A dedicated `snapshot.py` assembly over `build_run_views`, not a new read path
The snapshot is assembled in a new `atlas_conductor/gui/snapshot.py` that calls the existing
`build_run_views(reader)` and, per `RunView`, serializes verdicts/trace/counts (reusing the
shape `export.run_view_to_dict` already produces) **plus** `choreography_state(view.events)`
and `message_flow_state(view.message_flow)` as plain dicts. Rationale: the derivations already
exist and are tested; the snapshot is their single serialization point, so the payload cannot
diverge from what the GUI derives at render time.
- *Alternative considered:* compute the derived state inside `model.py` on `RunView`. Rejected —
  it would pull choreography/messageflow imports into the shared model and change the phase-3
  `RunView` contract; a separate assembly keeps `model.py` frozen.

### D-SNAP-2 — Explicit `SNAPSHOT_SCHEMA_VERSION`, top-level on the payload
The payload is `{"schema_version": SNAPSHOT_SCHEMA_VERSION, "runs": [...]}`. The version is an
integer constant in `snapshot.py`, bumped only on a breaking shape change, and is the value
phase 9 pins. Rationale: a renderer built against a frozen contract needs a cheap compatibility
check; a top-level version is the smallest thing that gives phase 9 a stable handle and a
migration signal.
- *Alternative considered:* semantic version string or per-run versions. Rejected — one
  integer for the whole payload is sufficient for a single-producer/single-consumer contract
  and avoids per-run bookkeeping.

### D-SNAP-3 — The JSON export *is* the snapshot (unify, don't duplicate)
`export_json` is redefined to emit `assemble_snapshot(...)`; `export_report(..., fmt="json")`
therefore returns the versioned snapshot. The old partial `run_view_to_dict`-only JSON shape is
dropped (**BREAKING**, but with no external consumer — the HTML export and the Streamlit GUI do
not parse the JSON). The HTML sibling keeps its own assembly from `build_run_views`, and a test
asserts HTML and JSON agree on verdicts/counts. Rationale: D18 wanted "the same data in another
shape"; one snapshot is that shape, and unifying removes the drift risk of two serializers.
- *Alternative considered:* keep the old JSON export and add a second `snapshot` output. Rejected
  — two machine-readable JSON shapes is exactly the divergence this phase exists to prevent.

### D-SNAP-4 — Invariants are asserted on the payload, not just trusted from upstream
The snapshot carries the D18 invariants as a *tested contract*: PHI-free (a gated-run fixture
yields only pseudonymized stems, no raw identifier), no image/embedding keys, and no
confidence/probability/score token anywhere in the serialized payload. These are first-class
tests on `snapshot.py` output, mirroring the phase-3 AppTest guardrails, so a future field
addition that leaked a score or a raw stem fails the build. Rationale: the payload is the thing
phase 9 renders; its safety must be provable at the contract boundary, independent of the
renderer.

### D-SNAP-5 — Stay in the streamlit-free, `atlas_patch`-free import zone
`snapshot.py` imports only `reader`, `model`, `choreography`, `messageflow`, and `trace` — all
already dependency-free — and never `streamlit` or `atlas_patch`. The existing CI import-guard
(importing `atlas_conductor.cli` pulls in no `streamlit`) continues to hold, and a companion
assertion covers `snapshot.py`. Rationale: preserves the PROJECT.md lean-install constraint and
keeps the contract consumable by any renderer (including phase 9's build tooling) without the
GUI runtime.

## Risks / Trade-offs

- **Breaking the JSON export shape with no deprecation window** → No external consumer exists
  (the CLI `export-report` is new this project and the JSON is not parsed by the HTML export or
  GUI); the change is documented in the README/CLI help and the `report-export` spec delta.
- **Derived state in the payload drifting from render-time derivation** → The snapshot calls the
  *same* `choreography_state` / `message_flow_state` functions the GUI uses; there is one
  derivation, serialized once, not a reimplementation.
- **A future field leaks a score or raw stem into the frozen contract** → First-class payload
  invariant tests (D-SNAP-4) fail the build on any such addition, exactly as the phase-3
  guardrails do for the renderer.
- **Schema version left un-bumped on a breaking change** → Phase 9 pins the version; a
  round-trip/shape test on the payload keys makes an unversioned breaking change visible in CI.
- **Reader/sink family filename drift** → Unchanged from phase 3: the reader derives family
  filenames from the sink's own mapping, and the round-trip test (sink writes → reader reads →
  snapshot) covers the whole path.

## Migration Plan

Purely additive plus one internal re-point. New `atlas_conductor/gui/snapshot.py` and its tests;
`export.py`'s JSON path calls it. No telemetry, CLI-surface, or `atlas_patch` change; the only
observable change is the JSON export's richer, versioned shape (README + CLI help updated).
Rollback is removing `snapshot.py` and restoring `export_json`'s previous body — no data or
schema migration. Phase 9 then consumes the frozen payload; nothing in this phase depends on
phase 9 landing.

## Open Questions

- Whether the snapshot should also expose a top-level `agents` roster (the `AGENTS` tuple) so a
  renderer need not hardcode agent order — leaning yes (cheap, and it frees phase 9 from
  duplicating the list); resolve during apply.
- Whether `export.py`'s HTML path should later also be regenerated from the snapshot dict rather
  than from `build_run_views` directly — out of scope here (HTML is unchanged this phase), noted
  for phase 9 when the React SPA subsumes the HTML sibling.
