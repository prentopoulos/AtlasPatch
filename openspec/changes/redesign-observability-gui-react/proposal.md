## Why

Phase 3 shipped the observability surface as a Streamlit app; phase 8 froze the
Python→renderer seam as a single versioned `gui-snapshot` payload (`SNAPSHOT_SCHEMA_VERSION = 1`).
Streamlit was the right scaffold to prove the panels, but it caps the visual and interaction
quality the operational surface can reach and re-renders server-side on every interaction. With
the contract now frozen, the renderer can be rebuilt as a static, taste-driven React SPA against
that stable payload — without touching a single governance invariant.

## What Changes

- Replace the Streamlit observability GUI with a refined React single-page app (Vite +
  TypeScript + Tailwind + shadcn/ui, design system from taste + `ui-ux-pro-max` skills) that
  renders the phase-8 frozen `gui-snapshot` payload and pins `SNAPSHOT_SCHEMA_VERSION`.
- The SPA is a **static, point-in-time renderer**: it imports no Python, no `atlas_patch`, and
  reads no telemetry directory — it consumes one pre-scrubbed `snapshot.json`. It ships with a
  committed demo snapshot for the out-of-the-box view **and** a file-picker / drag-drop loader
  for a real exported snapshot. Zero server. Client-polling live choreography is **deferred**.
- Panels (parity with the retired app, refined): a semantic verdict system
  (valid / skipped / quarantined / blocked → color-token system), KPI stat-tiles for cohort
  metrics, a sortable per-slide verdict table, a decision-trace tree, run history, and the
  agent-choreography view (Level-1 component-state + Level-2 message-flow) with tasteful on-load
  motion.
- **BREAKING (internal):** retire the Streamlit renderer — remove `atlas_conductor/gui/app.py`,
  drop the `streamlit>=1.30` runtime dependency, and remove Streamlit from the CI `app` job. The
  snapshot-producer modules (`reader`, `model`, `choreography`, `messageflow`, `snapshot`,
  `export`) are **untouched** — they remain the single read path behind the contract.
- **Spec correction in the MODIFY:** narrow the phase-3 "no image element is ever rendered"
  scenario from *"no image element is produced by the app"* to *"no slide pixel, mask, or heatmap
  image is rendered."* A shadcn/ui SPA legitimately uses SVG chrome icons; the invariant's intent
  is no **slide imagery**, not no `<svg>`. The re-homed guardrail targets slide imagery.
- Re-home the phase-3 Streamlit `AppTest` guardrails (no slide image, no confidence/diagnostic
  score, PHI-free identifiers, no control affordance) to **Vitest + Playwright** DOM guardrails on
  the React output.
- **Packaging:** vendor the prebuilt `dist/` (committed to git) and ship it in the wheel via
  `package-data`, so `pip install` stays Node-free. A new CI **`web`** job (Node 20) runs
  `npm ci` → `vitest run` → Playwright DOM guardrails → `vite build` → asserts the committed
  `dist/` matches the fresh build (build-and-diff). The Python `app` job stays, minus Streamlit.

## Capabilities

### New Capabilities

<!-- None. The React SPA is a new implementation of the existing observability-gui capability,
     not a new capability. The frozen data contract lives in the phase-8 gui-snapshot spec,
     which is unchanged. -->

### Modified Capabilities

- `observability-gui`: the renderer moves from Streamlit to a static React SPA over the frozen
  `gui-snapshot` payload. The read-only / no-slide-pixel / no-score / PHI-free / no-pipeline-import
  requirements are preserved but re-expressed for a static SPA that reads a snapshot rather than a
  telemetry directory; the "no image element" scenario is narrowed to slide imagery; the enforcing
  guardrails re-home from `AppTest` to Vitest + Playwright.

## Impact

- **Removed:** `atlas_conductor/gui/app.py`, the `streamlit>=1.30` dependency, the
  `tests/conductor/test_gui_app.py` `AppTest` suite, and Streamlit install/steps in CI's `app` job.
- **Unchanged:** every snapshot-producer module (`reader`/`model`/`choreography`/`messageflow`/
  `snapshot`/`export`), the `gui-snapshot` and `report-export` specs, and the whole `atlas_patch`
  pipeline. The frozen payload and its invariant tests are the seam this phase builds against.
- **Added:** a React SPA project (Vite/TS/Tailwind/shadcn) under the repo, a committed demo
  `snapshot.json` fixture, a vendored prebuilt `dist/`, `package-data` entry for the wheel, a
  Vitest + Playwright guardrail suite, and a Node-20 CI `web` job.
- **Install:** `pip install atlas-patch` stays Node-free and now Streamlit-free; the operational
  GUI is a static bundle served from the wheel or opened directly. No `atlas_patch`, GPU, model
  weight, or slide file is required to run it.
