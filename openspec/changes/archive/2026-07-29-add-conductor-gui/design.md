## Context

Phase 1 shipped the deterministic operational core with a typed, append-only, metadata-only
telemetry sink (`atlas_conductor/telemetry.py`) exposing four record families — `jobs`,
`slide_stage_outcomes`, `validation_results`, `agent_events` — with a JSONL local backend
(`JsonlTelemetrySink`) and an in-memory backend for tests. Phase 2 added the PHI-free write
gate, so persisted slide stems are pseudonymized when gating is on. The terminal report
(`atlas_conductor/report.py`) and the on-demand decision trace (`atlas_conductor/trace.py`)
already render off these records.

Design D18 (archived `add-atlas-conductor/design.md`) reserved this phase: a read-only
Streamlit GUI as an **additive renderer** over the telemetry sink — another renderer
alongside the terminal report — that **tails** the append-only families rather than hooking
the orchestrator, imports nothing from `atlas_patch`, and never shows slide pixels. It also
resolved two D18 open items that land here: the Level-1 component-state choreography view
(from `agent_events`) and an HTML/JSON sibling of the terminal report.

## Goals / Non-Goals

**Goals:**
- A read-only Streamlit GUI over the existing JSONL telemetry: run history, per-slide
  verdicts, decision trace, cohort metrics.
- Level-1 agent choreography (lit/dim component-state + now-processing ticker) from
  `agent_events`, working with the plain in-process components (no A2A).
- An HTML/JSON report sibling sharing the GUI's telemetry read path.
- CI-grade proof via `streamlit.testing.v1.AppTest` asserting the D18 guardrails (no image
  element, verdicts without scores, panels populate from PHI-free records).
- Keep `pip install atlas-patch` and the core `atlaspatch` CLI free of `streamlit`.

**Non-Goals:**
- Any control affordance — job submission, HITL confirmation, telemetry writes. Read-only.
- Level-2 A2A message-flow (deferred to phase 4; needs the A2A transport).
- A BigQuery-backed read path (phase 4). The GUI reads the local JSONL backend for now.
- Rendering slide pixels, masks, heatmaps, or any confidence/diagnostic score.
- Touching `atlas_patch/` internals or the telemetry record shapes.

## Decisions

### D-GUI-1 — Tail the JSONL families through a read-only reader, not the sink object
The GUI reads telemetry via a small **read-only reader** that opens the JSONL family files
(`jobs.jsonl`, `slide_stage_outcomes.jsonl`, `validation_results.jsonl`,
`agent_events.jsonl`) and returns rows as plain dicts, reusing the family filenames already
declared on `JsonlTelemetrySink`. It does not instantiate a live sink or call into the
orchestrator. Rationale: the sink is append-only and process-local; a separate reader keeps
the observer fully decoupled (D18 "tails … rather than hooking the orchestrator") and makes
the "no writes" invariant structural — the reader exposes no append method.
- *Alternative considered:* add read methods to the live sink and share an instance. Rejected
  — couples the GUI process to the orchestrator lifecycle and puts a write-capable object in
  the read-only surface.

### D-GUI-2 — `atlas_conductor/gui/` package, launched via a thin entry, streamlit guarded
The GUI lives in `atlas_conductor/gui/` with an `app.py` Streamlit script plus a `reader.py`
(the D-GUI-1 reader) and a `choreography.py` (agent-state derivation). `streamlit` is added
to the `orchestrator` extra and imported **only** inside the GUI package, never from
`atlas_conductor/cli.py`, `telemetry.py`, or the core path — matching how the extra already
guards ADK/A2A/BigQuery. A launch shim (`atlaspatch-conduct gui` subcommand or a documented
`streamlit run atlas_conductor/gui/app.py`) starts it. Rationale: keeps the core CLI import
graph free of streamlit so `pip install atlas-patch` is unchanged (PROJECT.md constraint).
- *Alternative considered:* a top-level `gui.py`. Rejected — the reader + choreography +
  export helpers want their own module boundary and a test target.

### D-GUI-3 — Verification split: AppTest in CI, browser render local-only
CI proof uses `streamlit.testing.v1.AppTest` — `AppTest.from_file(app).run()` then assert on
the element tree (`at.markdown`, `at.dataframe`, `at.exception`, `at.session_state`). The
suite feeds a fixture telemetry directory (built from the in-memory sink's records written to
JSONL, or hand-authored rows) and asserts the D18 guardrails directly: **no image element is
ever produced**, verdict panels show reason codes with **no** confidence/probability token,
and panels populate from PHI-free rows (pseudonymized stems, no raw identifiers). No browser,
server, or GPU, so it runs in the existing `app` CI job once the `orchestrator` extra is
installed there. Real-render confirmation (Chrome via the `run` + `claude-in-chrome` skills,
plus a choreography GIF) is a documented **manual** pass, not CI.
- *Alternative considered:* Selenium/Playwright end-to-end in CI. Rejected — needs a running
  server and a browser in CI for little added assurance over AppTest's element-tree checks;
  the visual confirmation is better done as a deliberate local pass.

### D-GUI-4 — Choreography state is derived, not a new record family
Level-1 lit/dim state and the now-processing ticker are **computed** from the existing
`agent_events` rows (the most-recent actor per run, plus the latest slide/stage), not backed
by a new telemetry family. Rationale: D18 says Level 1 is driven by tailing `agent_events`
and "needs no A2A" — deriving keeps the telemetry contract frozen and avoids a schema change
this phase. A new `agent_messages`/`agent_decisions` split stays an open D18 item for phase 4.

### D-GUI-5 — Report export reuses the report/trace data assembly
The HTML/JSON sibling is assembled from the same per-slide outcome + trace data the terminal
report builds (`report.py` / `trace.py`), serialized rather than pretty-printed. The GUI's
verdict/trace panels consume the same assembled structure, so export and GUI cannot diverge
(report-export spec). Rationale: "same audit/telemetry data in another shape" (D18); a shared
assembly is the single source that both the terminal, the file export, and the GUI render.

## Risks / Trade-offs

- **Streamlit leaking into the core import graph** → Import `streamlit` only inside
  `atlas_conductor/gui/`; add a CI import-guard test that importing `atlas_conductor.cli`
  pulls in no `streamlit` module (mirrors the phase-2 no-array/egress guards).
- **A future panel accidentally renders an image or a score, silently breaking a D18
  invariant** → The AppTest guardrail assertions (no image element, no confidence token) are
  first-class tests, not incidental; they fail the build if any panel regresses.
- **AppTest's element-tree API drifts across Streamlit versions** → Pin a `streamlit` lower
  bound in the `orchestrator` extra and keep assertions to stable element accessors
  (`markdown`, `dataframe`, `exception`); the visual manual pass is the backstop.
- **Reader and sink filename drift** (families renamed in the sink but not the reader) →
  Reader derives family filenames from the same mapping the sink declares, so a rename can't
  silently desync; a fixture round-trip test (sink writes → reader reads) covers it.
- **PHI leak via a raw stem shown in the GUI** → The GUI only ever displays the persisted
  identifier; an AppTest asserts a gated-run fixture renders pseudonyms and no raw stem.

## Migration Plan

Purely additive. New `atlas_conductor/gui/` package, a `streamlit` entry in the
`orchestrator` extra, and the report-export module/extension. No telemetry, CLI, or
`atlas_patch` changes, so there is nothing to roll back beyond removing the new files and the
extra entry. CI gains an AppTest suite and an import-guard test in the existing `app` job.

## Open Questions

- Launch surface: a first-class `atlaspatch-conduct gui` subcommand vs. a documented
  `streamlit run …` invocation. Leaning subcommand for discoverability; resolve during apply.
- Report-export format default: emit both HTML and JSON, or JSON first with HTML as a thin
  template over it. Leaning JSON-first (the machine-readable sibling D18 named), HTML as a
  render of the same structure.
