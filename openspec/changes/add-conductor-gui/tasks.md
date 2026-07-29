## 1. Packaging & telemetry read path

- [ ] 1.1 Add `streamlit` (with a pinned lower bound) to the `orchestrator` optional-dependency extra in `pyproject.toml`; note in the comment that it is imported only inside `atlas_conductor/gui/`.
- [ ] 1.2 Create the `atlas_conductor/gui/` package and add `reader.py`: a read-only telemetry reader that opens the JSONL family files (`jobs`, `slide_stage_outcomes`, `validation_results`, `agent_events`) and returns rows as dicts, deriving filenames from the same mapping `JsonlTelemetrySink` declares. No append/write method (D-GUI-1).
- [ ] 1.3 Unit-test the reader: write records through `JsonlTelemetrySink` to a temp dir, read them back with the reader, assert round-trip equality per family and a clean empty-state when files are absent.

## 2. Report export (shared read surface)

- [ ] 2.1 Add a report-export module (or extend `atlas_conductor/report.py`) that assembles the per-slide outcomes + reason codes + decision traces + cohort counts once, and serializes a JSON sibling of the terminal report (D-GUI-5, report-export spec).
- [ ] 2.2 Add an HTML rendering of the same assembled structure so HTML and JSON cannot diverge from each other or the terminal report.
- [ ] 2.3 Tests: JSON sibling mirrors the terminal report's outcomes and cohort counts; a gated run's export contains only PHI-free metadata (pseudonyms, verdicts, reason codes, counts) — no raw stem, pixel, mask, or embedding.

## 3. Observability GUI panels

- [ ] 3.1 Add `atlas_conductor/gui/app.py` — the Streamlit app shell that loads telemetry via the reader (import `streamlit` here only, never in the core path).
- [ ] 3.2 Run-history panel from `jobs`; per-slide verdict panel from `validation_results` + `slide_stage_outcomes` (structural verdict + reason code, no score); decision-trace panel from `agent_events`; cohort-metrics panel with valid/skipped/quarantined/blocked tallies (observability-gui spec).
- [ ] 3.3 Ensure the app renders a clean empty state when no runs exist and displays slide identifiers exactly as persisted (pseudonyms for gated runs), never re-deriving a raw stem.

## 4. Agent choreography (Level 1)

- [ ] 4.1 Add `atlas_conductor/gui/choreography.py`: derive per-agent lit/dim state and the latest slide/stage from `agent_events` (D-GUI-4) — no new telemetry family.
- [ ] 4.2 Render the four logical agents + scheduler as active/idle and a "now processing slide X · stage Y" ticker that follows the latest event and idles when no slide is active. Draw no inter-agent message edges (Level-2 out of scope, agent-choreography spec).

## 5. Launch surface

- [ ] 5.1 Provide the launch path — a `atlaspatch-conduct gui` subcommand that shells to `streamlit run atlas_conductor/gui/app.py` (or a documented direct invocation) — pointing at a telemetry directory. Resolve the D-GUI-2 open question here.

## 6. CI-grade verification (AppTest)

- [ ] 6.1 Add a `streamlit.testing.v1.AppTest` suite: build a fixture telemetry dir, `AppTest.from_file(app).run()`, assert history/verdict/trace/metrics panels populate from the fixture rows and no `at.exception` is raised.
- [ ] 6.2 Guardrail assertions (D18): no image element is ever produced by the app; verdict panels contain reason codes and no confidence/probability token; a gated-run fixture renders pseudonyms and no raw stem.
- [ ] 6.3 Choreography AppTest: given `agent_events` with a known latest actor, assert the right agent is active, others idle, and the ticker shows the expected slide/stage.
- [ ] 6.4 Import-guard test: importing `atlas_conductor.cli` (the core path) pulls in no `streamlit` module — mirrors the phase-2 no-array/egress guards.
- [ ] 6.5 Ensure the CI `app` job installs the `orchestrator` extra so the AppTest suite runs; confirm the suite is green with no browser/server/GPU.

## 7. Local visual confirmation & docs

- [ ] 7.1 Launch the GUI locally (the `run` skill / `streamlit run`), drive a real Chrome tab via `claude-in-chrome`: screenshot the panels, read console/network for errors, and record a `gif_creator` clip of the Level-1 choreography lighting up (agents dim→lit). This is a manual pass, not CI.
- [ ] 7.2 Document the GUI in the README/PROJECT notes: what it renders, the read-only + PHI-free guarantees, the launch command, and that Level-2 message-flow is deferred to phase 4.
