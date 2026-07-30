## 1. Slice A — scaffold + snapshot-load skeleton (green in CI)

- [ ] 1.1 Scaffold the Vite + TypeScript + React project at repo-root `web/` (`package.json`, `tsconfig`, `vite.config.ts`, `package-lock.json`); set `vite build` `outDir` to `../atlas_conductor/gui/web_dist`.
- [ ] 1.2 Add and configure Tailwind CSS and initialize shadcn/ui (Radix + Tailwind primitives) with a base theme.
- [ ] 1.3 Define the payload TypeScript types mirroring the frozen snapshot shape (`schema_version`, `agents`, `runs[].{job_id, job, cohort_size, counts, slides[].{slide_stem, outcome, reason_code, detail, trace}, choreography, message_flow}`) and a `SNAPSHOT_SCHEMA_VERSION` constant pinned to `1`.
- [ ] 1.4 Generate a committed demo `snapshot.json` fixture by running `assemble_snapshot` over a seeded telemetry fixture (documented, reproducible), and bundle it as the default on-load view.
- [ ] 1.5 Implement snapshot loading: render the bundled demo with no input; add a file-picker + drag-drop loader that validates the top-level shape, compares `schema_version` to the pinned constant, and shows an explicit incompatibility state on mismatch and an error (not a crash) on a malformed file.
- [ ] 1.6 Render the run-history panel from the runs' job rows (job id, status, cohort, per-outcome counts) plus a run selector; render an empty state for a zero-run snapshot.
- [ ] 1.7 Add the CI `web` job (`actions/setup-node@v4`, Node 20): `npm ci` → `vitest run` → `vite build`; add a first Vitest test asserting the demo snapshot loads and the history panel populates.

## 2. Slice B — panels + design system (green in CI)

- [ ] 2.1 Define the semantic verdict token system (Tailwind theme tokens for `valid`/`skipped`/`quarantined`/`blocked`) and reusable verdict `Badge`, used consistently across panels.
- [ ] 2.2 Build the cohort-metrics KPI stat-tiles (cohort size + valid/skipped/quarantined/blocked tallies) from `counts`.
- [ ] 2.3 Build the sortable per-slide verdict table (shadcn `Table`) showing pseudonymized stem, structural verdict, reason code, and detail — no score column, sortable by column.
- [ ] 2.4 Build the decision-trace tree (collapsible) from each slide's `trace`.
- [ ] 2.5 Build the agent-choreography panel: Level-1 component-state (per-agent active/idle + now-processing) and Level-2 message-flow (directed edges with counts; degrade cleanly to component-state-only when `message_flow` has no flow), driven by the payload's `agents`, `choreography`, and `message_flow`.
- [ ] 2.6 Add Vitest render tests for each panel (populate from the demo fixture; sorting; trace tree; empty and no-message-flow states).

## 3. Slice C — motion, guardrails, vendored dist, Streamlit retirement (green in CI)

- [ ] 3.1 Add tasteful on-load/enter motion to the stat-tiles, table rows, and choreography markers (CSS/Tailwind transitions or a lightweight primitive) — on-load only, no polling, nothing implying live data.
- [ ] 3.2 Add a gated-run demo fixture (pseudonymized stems) alongside the default demo for the safety guardrails.
- [ ] 3.3 Add the Playwright DOM guardrail suite over the demo and the gated fixture: no slide pixel/mask/heatmap image or canvas (decorative SVG chrome excluded by selector intent); no confidence/probability/diagnostic-score text anywhere in the DOM; only pseudonymized stems (no raw-identifier pattern); no control that submits, confirms, or writes.
- [ ] 3.4 Wire Playwright into the CI `web` job (after Vitest, before/around `vite build`) and confirm it runs headless.
- [ ] 3.5 Build and commit the vendored `atlas_conductor/gui/web_dist/`; declare it as `package-data` under `atlas_conductor.gui` in `pyproject.toml` so the wheel ships it and `pip install` stays Node-free.
- [ ] 3.6 Add the CI build-and-diff step: rebuild from `web/` and assert the committed `web_dist/` is byte-identical (fail on drift).
- [ ] 3.7 Retire Streamlit: delete `atlas_conductor/gui/app.py` and `tests/conductor/test_gui_app.py`, remove `streamlit>=1.30` from `pyproject.toml`, and remove the Streamlit install + AppTest step from the CI `app` job.
- [ ] 3.8 Confirm the producer modules (`reader`/`model`/`choreography`/`messageflow`/`snapshot`/`export`/`trace`) and the `gui-snapshot` + `report-export` specs are untouched.

## 4. Verification & docs

- [ ] 4.1 Update the README / GUI docs to describe the static React observability GUI: how it is served from the wheel, the bundled demo, and the snapshot file loader (replacing the Streamlit run instructions).
- [ ] 4.2 Confirm `pip install -e . --no-deps` and `atlaspatch-conduct --version` still work with Streamlit gone, and that the CLI import graph pulls in no `streamlit`.
- [ ] 4.3 Run the full local gate — `ruff check`, `pytest tests/conductor -q`, `npm run` Vitest + Playwright, `vite build` + build-and-diff, and `openspec validate --all --strict` — and confirm all green before opening for merge.
