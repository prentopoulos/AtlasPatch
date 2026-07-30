## Why

Phase 3 shipped a read-only Streamlit observability GUI that assembles each run's state at
render time (`build_run_views`, `choreography_state`, `message_flow_state`) and — separately —
an HTML/JSON report sibling that re-serializes part of that same structure. The two surfaces
share the read path but not a single, complete, versioned payload: the JSON export omits the
derived choreography and message-flow state entirely, and there is no frozen contract any
other renderer could consume. Phase 9 will replace the Streamlit renderer with a React SPA,
which needs exactly such a contract. This phase freezes that seam **before** any renderer is
built against it, so the risky Python↔renderer boundary is settled and round-trip verified on
its own, and even if phase 9 slipped, the richer machine-readable export ships value now.

## What Changes

- Add a single, schema-**versioned** `snapshot` assembly in the GUI package that serializes a
  telemetry directory into one JSON-safe payload carrying everything the observability surface
  shows: run history (jobs), per-slide verdicts (structural outcome + reason code + detail),
  decision trace (from `agent_events`), cohort metrics (valid/skipped/quarantined/blocked
  tallies), and the **derived** Level-1 component-state choreography and Level-2 message-flow
  state that today are computed only at Streamlit render time.
- Unify the JSON report export onto this snapshot: `export_report(..., fmt="json")` emits the
  versioned snapshot rather than the current partial `{"runs": [...]}` shape. The HTML sibling
  continues to render the same assembled data. **BREAKING** for any consumer parsing the old
  JSON export shape (there is no external consumer today; the HTML export and the GUI are
  unaffected).
- Carry the D18/observability invariants into the payload as a contract: PHI-free (slide stems
  exactly as persisted — pseudonyms for gated runs, never a raw identifier), no pixels/masks,
  and no confidence/probability/diagnostic score — verdicts are structural pass/fail plus a
  reason code only.
- Round-trip verification: an in-memory sink's records written to JSONL, read back through the
  reader, and assembled into a snapshot reproduce the recorded verdicts, counts, trace, and
  derived state.
- Keep the assembly in the GUI package's dependency-free helpers (reader / model /
  choreography / messageflow), so the core CLI import graph pulls in no `streamlit` and no
  `atlas_patch`. The Streamlit `app.py` is **untouched** this phase.

## Capabilities

### New Capabilities
- `gui-snapshot`: The frozen, schema-versioned observability snapshot — one JSON-safe payload
  assembled from the PHI-free telemetry that is the single machine-readable contract every
  observability renderer consumes. Defines the payload's shape (schema version, runs, per-slide
  verdicts, decision trace, cohort metrics, derived choreography and message-flow state), its
  invariants (PHI-free, no pixels, no scores), and its round-trip fidelity against the reader.

### Modified Capabilities
- `report-export`: The JSON sibling is redefined to **be** the `gui-snapshot` payload (the
  single machine-readable shape), rather than a separate partial serialization. The existing
  requirements — sourced from the same telemetry read path as the GUI, PHI-free, no pixels —
  are preserved and now satisfied by emitting the snapshot.

## Impact

- **Code**: new `atlas_conductor/gui/snapshot.py` (the assembly + schema version); `export.py`
  JSON path re-pointed at it; new tests under `tests/conductor/`. No change to `app.py`,
  `reader.py`, `model.py`, `choreography.py`, `messageflow.py` interfaces (they are read/reused).
- **Contract**: introduces a `SNAPSHOT_SCHEMA_VERSION` that phase 9's React renderer will pin.
- **Dependencies**: none added — pure-Python `json` assembly; no Node, no `streamlit`, no
  `atlas_patch`. Verified by the existing `app` CI job (pytest) plus the streamlit-free
  import-guard already in place.
- **Docs**: README export note and the `export-report` CLI help updated to describe the
  versioned snapshot; `PROJECT.md` phase 8 row (already added) tracks status.
