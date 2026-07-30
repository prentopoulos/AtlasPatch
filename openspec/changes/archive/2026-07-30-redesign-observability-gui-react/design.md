## Context

Phase 3 (`add-conductor-gui`, design D18) shipped the observability surface as a Streamlit app
(`atlas_conductor/gui/app.py`) over five dependency-free helpers (`reader`, `model`,
`choreography`, `messageflow`, and the `trace` renderer). Phase 8 (`add-gui-snapshot-contract`,
design D-SNAP-*) froze the Python→renderer seam: `atlas_conductor/gui/snapshot.py` assembles a
telemetry directory into one JSON-safe, schema-versioned payload —
`{schema_version, agents, runs:[{job_id, job, cohort_size, counts, slides, choreography,
message_flow}]}` at `SNAPSHOT_SCHEMA_VERSION = 1` — that carries every observability section a
renderer needs, with the D18 invariants asserted as first-class payload tests (PHI-free, no
image/embedding, no score).

With that contract frozen, the renderer is now the only moving part. This phase rebuilds it as a
static React SPA and retires Streamlit. The SPA is a *pure consumer of the payload*: it never
imports Python, never reads a telemetry directory, and runs with no server. Every governance
invariant is preserved — most of them by construction, since a static client rendering a
pre-scrubbed JSON cannot reach a slide file, a model weight, or a raw identifier.

Constraints carried from `PROJECT.md`: `atlas_patch/` is untouched; the telemetry stays
metadata-only/PHI-free; the surface is operational, not clinical (structural verdicts, no scores);
and `pip install atlas-patch` must remain lean — here, specifically, **Node-free**.

## Goals / Non-Goals

**Goals:**
- A refined React SPA (Vite + TypeScript + Tailwind + shadcn/ui) rendering the phase-8 payload:
  run history, sortable per-slide verdict table, decision-trace tree, KPI stat-tiles for cohort
  metrics, and the Level-1/Level-2 agent-choreography, with tasteful on-load motion.
- The SPA pins `SNAPSHOT_SCHEMA_VERSION` and shows an explicit incompatibility state on mismatch.
- Point-in-time data delivery: a committed demo `snapshot.json` for the out-of-the-box view plus a
  file-picker / drag-drop loader for a real exported snapshot. No server, no polling.
- Re-home the phase-3 renderer guardrails (no slide image, no score, PHI-free identity, no control
  affordance) to Vitest + Playwright DOM assertions on the React output.
- Retire Streamlit end-to-end: delete `app.py`, drop the `streamlit` dependency, and remove it
  from the CI `app` job — leaving every snapshot-producer module untouched.
- Ship a vendored prebuilt bundle in the wheel so install stays Node-free, with CI proving the
  committed build matches source (build-and-diff).

**Non-Goals:**
- Any change to the frozen `gui-snapshot` payload, its `SNAPSHOT_SCHEMA_VERSION`, or any producer
  module (`reader`/`model`/`choreography`/`messageflow`/`snapshot`/`export`). The seam is frozen;
  this phase consumes it.
- Live / streaming / client-polling choreography. The SPA renders a point-in-time snapshot,
  matching today's refresh-to-update behavior; polling is deferred to a possible later phase.
- Any telemetry, CLI-surface, or `atlas_patch` change.
- Rendering slide pixels, masks, heatmaps, or any confidence/diagnostic score — forbidden in the
  renderer as in the payload.
- Re-implementing the HTML export sibling in React (the `report-export` HTML path is out of scope;
  it stays as the phase-8 assembly).

## Decisions

### D-REACT-1 — SPA source at repo-root `web/`, built output vendored under the Python package
The Vite/TS project lives at repo-root `web/` (its own `package.json`, `src/`, tests, `node_modules`);
`vite build` emits into `atlas_conductor/gui/web_dist/`, which is **committed to git** and shipped
in the wheel. Rationale: keeping the JS toolchain (`node_modules`, `src`, config) *outside* the
importable Python package keeps the package tree clean and prevents source/`node_modules` from
leaking into the sdist, while the built assets land *inside* the package so `package-data` can
carry them. `web_dist/` is the single vendored artifact.
- *Alternative considered:* co-locate source and build under `atlas_conductor/gui/web/`. Rejected —
  `node_modules` and TS source inside the package tree invite accidental packaging and muddy the
  import-guard story.
- *Alternative considered:* a separate repo/package for the GUI. Rejected — the phase must ship the
  bundle in the same wheel (`PROJECT.md` lean-install), and one repo keeps the snapshot contract and
  its renderer versioned together.

### D-REACT-2 — Point-in-time data model: bundled demo + file loader, schema-version pinned
The SPA holds the loaded snapshot in client state. On first load it renders a committed demo
`snapshot.json` (bundled at build time from a fixture) so the panels populate with zero input; a
file-picker + drag-drop zone lets an operator load a real exported `snapshot.json`, which replaces
the run set. The loader validates the top-level shape and compares `schema_version` to a pinned
constant (`SNAPSHOT_SCHEMA_VERSION = 1` mirrored in TS); a mismatch or malformed file yields an
explicit state, never a crash or a mis-render. No `fetch` to a server, no polling. Rationale: this
is exactly the phase-8 "point-in-time serialization" contract and today's refresh-to-update model;
a static client with a bundled demo is demoable offline and needs no backend.
- *Alternative considered:* fetch a snapshot from a `?src=` URL. Rejected as the default — it needs
  a host and yields a blank first paint; a `?src=` convenience could be added later without changing
  the contract.
- *Alternative considered:* embed the snapshot at build time only. Rejected — an operator must be
  able to view *their* exported run without a rebuild.

### D-REACT-3 — Semantic verdict system as the design spine (Tailwind tokens + shadcn/ui)
The four terminal outcomes (`valid` / `skipped` / `quarantined` / `blocked`) drive a semantic color
+ token system defined once (Tailwind theme tokens) and reused across the stat-tiles, the verdict
table's status cells, and the choreography markers — so a verdict reads the same everywhere.
Primitives come from shadcn/ui (Radix + Tailwind): a sortable `Table`, `Card`/stat-tiles, a
collapsible tree for the trace, and `Badge` for verdicts. The design system is developed with the
`ui-ux-pro-max` skill and taste, staying inside an operational (not marketing) register. Rationale:
one token layer keyed on the domain's own enum is the smallest thing that makes the surface cohere
and keeps "structural verdict, not score" legible; shadcn/ui gives accessible, themeable primitives
without a heavy component dependency.
- *Alternative considered:* a full component library (MUI/AntD). Rejected — heavier, harder to theme
  to a custom operational look, and more than a five-panel surface needs.

### D-REACT-4 — Guardrails re-home to Vitest (unit/render) + Playwright (DOM invariants)
The phase-3 `AppTest` guards become two layers: **Vitest + Testing Library** for component/render
logic (panels populate from a fixture; empty/mismatch/malformed states; sorting; trace tree), and
**Playwright** for the safety invariants asserted on the rendered DOM against the demo *and* a
gated-run fixture — no `<img>`/canvas carrying slide data (chrome SVG icons excluded by selector
intent), no confidence/probability/diagnostic-score text anywhere in the DOM, pseudonymized stems
only (no raw-identifier pattern), and no control that submits/confirms/writes. Rationale: the
payload's safety is proven at the contract boundary (phase-8 D-SNAP-4); the renderer's safety must
be proven on its *output*, mirroring the phase-3 guardrails one layer down. Two tools split the
concern cleanly: logic in jsdom, real-DOM invariants in a browser.
- *Alternative considered:* Playwright only. Rejected — component logic is cheaper and clearer in
  Vitest; Playwright is reserved for the DOM-level invariant proofs.

### D-REACT-5 — Vendored `dist/` in git + `package-data`, guarded by CI build-and-diff
`atlas_conductor/gui/web_dist/` is committed and declared as `package-data` (glob under
`atlas_conductor.gui`) so the wheel carries it and `pip install` needs no Node. Staleness is
prevented by a CI step that rebuilds from `web/` and asserts the working tree is clean (the fresh
build byte-matches the committed `web_dist/`); a drift fails the build. Rationale: `PROJECT.md`
requires a Node-free install, which means the built assets must live in the wheel; committing them
is the only way to keep the source-of-truth in the repo, and build-and-diff removes the "someone
forgot to rebuild" failure mode. Reproducible output is pinned via `package-lock.json` + a fixed
Node version.
- *Alternative considered:* build the bundle at `pip install` time. Rejected — forces Node onto
  every install, violating the lean-install constraint.
- *Alternative considered:* `.gitignore` the dist and build only in `publish.yml`. Rejected — then
  `pip install` from source (editable/dev) has no GUI, and the artifact the wheel ships is never
  reviewed in a PR.

### D-REACT-6 — A new Node-20 CI `web` job; the Python `app` job stays, minus Streamlit
CI gains a `web` job (`actions/setup-node@v4`, Node 20): `npm ci` → `vitest run` → Playwright DOM
guardrails → `vite build` → build-and-diff. The existing `app` job stays Python-only but drops the
`streamlit` install and the `AppTest` suite. The `specs` job is unchanged. Rationale: the two
toolchains stay in separate jobs so the Python install path is never Node-tainted and vice-versa;
the `app` job keeps proving the no-GPU orchestrator loop and the import-guard (now also that the CLI
pulls in no `streamlit`, trivially, since it is gone).

### D-REACT-7 — Retire Streamlit as a clean removal, producers untouched
Delete `atlas_conductor/gui/app.py` and `tests/conductor/test_gui_app.py`; remove `streamlit>=1.30`
from `pyproject.toml` and from the CI `app` job. Keep `reader.py`, `model.py`, `choreography.py`,
`messageflow.py`, `snapshot.py`, `export.py`, and the `trace` renderer exactly as-is — they are the
producer behind the frozen contract and have no Streamlit dependency. Rationale: the contract seam
is precisely the line that lets the renderer be swapped without disturbing the read path; retiring
Streamlit is a deletion, not a refactor.

### D-REACT-8 — Ship the one PR as three green-in-CI internal slices
Mirroring phase 1's A1/A2/A3, the single phase-9 PR is staged as three slices, each landing green:
- **Slice A — scaffold + skeleton:** the `web/` Vite/TS/Tailwind/shadcn project, the Node-20 CI
  `web` job, the schema-version pin and snapshot loader (bundled demo + file loader), and a
  run-history render. Establishes the toolchain and the data path end-to-end.
- **Slice B — panels + design system:** the verdict token system, KPI stat-tiles, sortable verdict
  table, decision-trace tree, and the Level-1/Level-2 choreography panel — full parity with the
  retired app, refined.
- **Slice C — motion, guardrails, vendored dist:** tasteful on-load motion, the re-homed
  Vitest/Playwright guardrail suite, the committed `web_dist/` + `package-data`, the build-and-diff
  gate, and the Streamlit retirement.
Rationale: a large renderer rewrite is reviewable in checkpoints that each keep CI green; the slice
boundaries fall on toolchain → surface → hardening, so no slice leaves the tree broken.

### D-REACT-9 — On-load motion only, no live/animated data
Motion is limited to tasteful on-load/enter transitions (stat-tiles, table rows, choreography
markers) via CSS/Tailwind transitions or a lightweight motion primitive. No motion implies live
data, no polling loop, no continuously animating choreography. Rationale: the snapshot is
point-in-time; motion should aid first-read hierarchy, not suggest a liveness the data does not have
(and the phase-8 non-goal of a streaming payload stands).

## Risks / Trade-offs

- **Committed build output drifts from source** → CI build-and-diff (D-REACT-5) fails on any
  mismatch; `package-lock.json` + pinned Node keep the build reproducible.
- **A future renderer field leaks a score, a raw stem, or a slide image** → Playwright DOM
  guardrails on the demo *and* a gated fixture (D-REACT-4) fail the build, mirroring the phase-3
  guards one layer down.
- **`node_modules` / TS source leaking into the wheel** → source lives at repo-root `web/`, outside
  the package tree; only `atlas_conductor/gui/web_dist/**` is declared `package-data` (D-REACT-1).
- **Schema drift between producer and renderer** → the SPA pins `SNAPSHOT_SCHEMA_VERSION` and shows
  an explicit incompatibility state (D-REACT-2); the version is a single integer the phase-8 payload
  already carries.
- **SVG chrome icons tripping a naive "no image" guard** → the spec scenario is narrowed to *slide*
  imagery and the Playwright selector targets slide-data image/canvas elements, not decorative
  `<svg>` (spec MODIFY + D-REACT-4).
- **Two CI toolchains slowing the pipeline** → `web` and `app` run as independent jobs; neither
  blocks the other and each stays single-purpose (D-REACT-6).
- **Losing the Streamlit surface before the React one is proven** → the retirement lands in Slice C,
  after the panels and guardrails are green (D-REACT-7/8), so `main` is never without a working GUI.

## Migration Plan

Additive plus one clean removal, staged as three slices on one branch (D-REACT-8). New `web/`
project and committed `atlas_conductor/gui/web_dist/`; `pyproject.toml` gains the `package-data`
glob and drops `streamlit`; CI gains the `web` job and the `app` job drops Streamlit. The Streamlit
`app.py` and its `AppTest` suite are deleted in the final slice. No telemetry, CLI-surface, or
`atlas_patch` change; the `gui-snapshot` and `report-export` contracts are untouched. Rollback is
reverting the branch — restoring `app.py` and the `streamlit` dependency — with no data or schema
migration, since nothing downstream of the frozen payload changed.

## Open Questions

- Whether to also accept a `?src=<path>` query param as a convenience snapshot source alongside the
  file loader — leaning defer (out of scope; the file loader + bundled demo satisfy the spec), noted
  for a later phase if a hosting story appears.
- Whether the phase-8 `report-export` HTML sibling should later be regenerated from the React build
  (a single rendering path) — out of scope here, carried over from the phase-8 open question.
- Exact motion primitive (pure CSS/Tailwind transitions vs. a small library) — resolve during Slice
  C against bundle-size and the on-load-only constraint (D-REACT-9).
