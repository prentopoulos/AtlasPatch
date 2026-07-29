## Why

The conductor already writes a rich, PHI-free telemetry stream (`jobs`,
`slide_stage_outcomes`, `validation_results`, `agent_events`), but the only way to observe
a run is the terminal report. Operators running cohorts at scale need a live, at-a-glance
view — which slides are valid, why others were quarantined/blocked, what each agent
decided, and what is being processed right now — without reaching for log files. Design D18
reserved exactly this: a read-only observability GUI that renders over the telemetry sink,
attachable now that the deterministic core (phase 1) and governance gate (phase 2) have
landed.

## What Changes

- Add a **read-only Streamlit GUI** (`atlas_conductor/gui/`) that renders over the existing
  PHI-free telemetry. It **tails** the append-only JSONL families rather than hooking the
  orchestrator process, imports nothing from `atlas_patch`, and never renders slide pixels.
- **Re-skinned clean-room** from a diagnostic dashboard into an operational one — every
  panel inverts clinical → operational: **verdicts not predictions**, **decision-trace not
  Grad-CAM**, cohort/run metrics not per-pixel heatmaps.
- Panels for the read-only MVP: **run history** (`jobs`), **per-slide verdict table**
  (`validation_results` + `slide_stage_outcomes`), **decision trace** (`agent_events`, the
  same chain-of-decisions the terminal report shows on demand), and **cohort metrics**.
- **Live agent-choreography view, Level 1 (component-state):** the four logical agents
  rendered lit (active) / dim (idle) with a "now processing slide X · stage Y" ticker,
  driven by tailing `agent_events`. Works from the plain in-process components; needs no
  A2A. **Level 2 message-flow is explicitly out of scope** (deferred to phase 4 — needs the
  A2A wiring).
- **Read-only only:** the GUI observes; it is **not** a control surface — no HITL
  confirmation, no job submission. Those remain later/CLI work.
- Resolve the D18-noted report task: an **HTML/JSON machine-readable sibling** of the
  terminal report, the same audit/telemetry data in another shape (and the seam the GUI
  reuses for its verdict/trace panels).
- Add `streamlit` to the `orchestrator` optional-dependency extra behind a guarded import
  so `pip install atlas-patch` and the core `atlaspatch` CLI are unaffected; the CI `app`
  job installs it to run the AppTest suite.
- **Verification:** CI-grade proof via Streamlit's native headless harness
  (`streamlit.testing.v1.AppTest`) asserting the D18 guardrails directly — no image element
  ever rendered, verdict text present with **no** confidence/probability score, panels
  populate from PHI-free records. Local visual confirmation (real Chrome render +
  choreography GIF) is a documented manual pass, not CI.

## Capabilities

### New Capabilities
- `observability-gui`: A read-only Streamlit renderer over the PHI-free telemetry —
  run-history, per-slide verdicts, decision trace, and cohort metrics panels; tails the
  append-only sink; imports nothing from `atlas_patch`; renders no slide pixels and no
  confidence scores.
- `agent-choreography`: The Level-1 component-state view — the four logical agents shown
  lit/dim with a "now processing" ticker, driven by tailing `agent_events`. Level-2
  message-flow is explicitly deferred to phase 4.
- `report-export`: An HTML/JSON machine-readable sibling of the terminal report, sourced
  from the same telemetry/audit records (resolves the D18 open item).

### Modified Capabilities
<!-- No existing capability's REQUIREMENTS change: the GUI is an additive renderer over the
     telemetry families defined by run-telemetry / phi-safe-telemetry. It reads those
     records but changes none of their requirements. -->

## Impact

- **New code:** `atlas_conductor/gui/` (Streamlit app + a telemetry tailer/reader that
  reads the JSONL families read-only); a report-export module (or an extension of
  `atlas_conductor/report.py`) emitting the HTML/JSON sibling.
- **Dependencies:** `streamlit` added to the `orchestrator` extra, guarded so it is never
  imported by the core CLI. No new core runtime dependency.
- **Tests / CI:** new `AppTest`-based suite in the `app` CI job; the job installs the
  `orchestrator` extra. No GPU, no browser, no server needed in CI.
- **Untouched:** `atlas_patch/` internals, the telemetry record shapes, and all phase-1/2
  invariants. The GUI is a pure additive reader — no orchestrator behavior changes.
