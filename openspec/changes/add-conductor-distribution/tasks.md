## 1. Message-flow telemetry family (D-DIST-3)

- [x] 1.1 Add a frozen `MessageFlowRecord` `(job_id, from_agent, to_agent, message_type, correlation_id, slide_stem?, stage?, timestamp)` to `atlas_conductor/telemetry.py`, scalars/enums/ids only — no array field.
- [x] 1.2 Add `record_message_flow` to the `TelemetrySink` ABC and implement it on `JsonlTelemetrySink` (new `message_flow.jsonl` file + `read_family` wiring) and `InMemoryTelemetrySink`.
- [x] 1.3 Extend the metadata-only-by-type test to `MessageFlowRecord` (asserting no image/array-accepting method exists) and assert `PhiSafeSink` pseudonymizes its `slide_stem` on the same path as the other families.

## 2. Agent-transport seam: interface + in-process (D-DIST-1, D-DIST-2)

- [x] 2.1 Create `atlas_conductor/transport/__init__.py` with an `AgentTransport` interface routing planner/worker/validator/recovery interactions, plus a `make_transport(name)` resolver mirroring `make_adapter`.
- [x] 2.2 Implement `InProcessTransport` calling the components directly and emitting one `MessageFlowRecord` per routed interaction, so outputs stay byte-identical to the current direct-call path.
- [x] 2.3 Wire `run.py`/`scheduler.py` agent call sites through the selected transport (default `in-process`) and add a `transport` selector to `config.py` (`JobConfig`), defaulting to in-process.
- [x] 2.4 Test: an in-process run records `message_flow` rows for each interaction and produces the same `RunResult` and family rows as the pre-change path (regression pin).

## 3. A2A transport (D-DIST-5, D-DIST-6)

- [ ] 3.1 Add `google-adk`, the A2A SDK, and `google-cloud-bigquery` to the `orchestrator` extra in `pyproject.toml` with pinned lower bounds.
- [ ] 3.2 Implement `atlas_conductor/transport/a2a.py`: expose the four agents as ADK/A2A peers on loopback with the scheduler as in-process client, importing the cloud SDKs only inside this module (guarded).
- [ ] 3.3 Make `A2ATransport` emit the same `MessageFlowRecord` shape from real peer messages, and raise a clear "install atlas-patch[orchestrator]" error when selected without the extra.
- [ ] 3.4 Add a thin loopback runner (subcommand or `python -m atlas_conductor.transport.a2a`) to start the peer set for a demo/real run; document it in the README.
- [ ] 3.5 Parity test: run the same job through `InProcessTransport` and a stubbed `A2ATransport`; assert identical per-slide `RunResult` and identical family rows modulo timestamps/correlation ids.

## 4. BigQuery telemetry backend (D-DIST-4)

- [ ] 4.1 Implement `BigQueryTelemetrySink(TelemetrySink)` mapping each family (incl. `message_flow`) to a table and each record to a row insert, importing `google-cloud-bigquery` behind a guard.
- [ ] 4.2 Add a `telemetry.backend` (+ dataset) selector to `config.py`, defaulting to `jsonl`; select the BigQuery sink only when explicitly configured.
- [ ] 4.3 Test against a fake BigQuery client: assert the inserted row for each family equals the JSONL row (modulo stamped timestamp), with no live connection.

## 5. GUI Level-2 message-flow view (agent-choreography delta)

- [ ] 5.1 Add `atlas_conductor/gui/messageflow.py`: derive directed `(from_agent, to_agent)` edges and per-edge recency from the `message_flow` family (read via the read-only reader).
- [ ] 5.2 Render a Level-2 panel in `gui/app.py` with the agent nodes + pulsing edges, and a degrade-to-Level-1 state ("no message flow recorded") when the run has no `message_flow` rows.
- [ ] 5.3 Extend the reader to expose the `message_flow` family and add an AppTest asserting: edges render for a run with rows, and the degrade state renders (no edges) for a run without them.

## 6. Packaging, import guard, and living specs

- [ ] 6.1 Extend the CI import-guard test to assert the core `atlaspatch` CLI import graph pulls in none of `google-adk`, the A2A SDK, or `google-cloud-bigquery`.
- [ ] 6.2 Run the full suite (mypy, ruff, pytest) green on the in-process transport + JSONL backend against the fake adapter; mark the loopback A2A test optional so SDK/install issues can't gate CI.
- [ ] 6.3 Update the README (transport + telemetry-backend selectors, A2A demo runner, BigQuery opt-in) and confirm `openspec validate add-conductor-distribution` passes.
