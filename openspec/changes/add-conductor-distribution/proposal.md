## Why

Phases 1–3 shipped the deterministic operational core as plain in-process components with a
metadata-only telemetry sink and a read-only GUI whose choreography view is Level 1 only
(lit/dim component-state). Design D8 deferred the actual **A2A agent wiring** and the
**BigQuery telemetry backend** to this phase, and the agent-choreography spec explicitly
holds the **Level-2 message-flow view** out of scope until an A2A transport exists. The core
never needed A2A for correctness — the four components produce identical outputs as direct
calls — so the protocol is adopted here for a *named* payoff: watchable inter-agent
choreography and a cohort-scale telemetry backend, adopted last, behind an optional extra, so
`pip install atlas-patch` and the green-in-CI in-process path are untouched.

## What Changes

- **Add an agent-transport seam** mirroring the existing real/fake adapter pattern: the run
  façade routes the four logical agents (planner, worker, validator, recovery) through an
  `AgentTransport` interface with an in-process default (identical to today's direct calls)
  and an opt-in A2A implementation on Google ADK + A2A. The scheduler stays a deterministic
  in-process governor, not a fifth agent (D8).
- **Emit a `message_flow` telemetry family** — typed, metadata-only, PHI-free — recording
  each inter-agent message `(from_agent, to_agent, message_type, correlation)`. Both
  transports emit it, so the Level-2 view and its CI proof do not require a live A2A network.
- **Add an opt-in BigQuery telemetry backend** (`BigQueryTelemetrySink`) behind the same
  append-only `TelemetrySink` interface, making concrete the backend the run-telemetry spec
  reserved. Local JSONL stays the credential-free default; switching backends changes nothing
  any agent records.
- **Add the GUI Level-2 message-flow view**: peer messages pulsing as edges between agent
  nodes, derived from the `message_flow` family, degrading to Level-1-only when a run has no
  message rows. Supersedes the choreography spec's "Level-2 out of scope" requirement.
- **Gate all heavy deps** (`google-adk`, `a2a`, `google-cloud-bigquery`) behind the
  `orchestrator` extra with guarded imports, enforced by the existing CI import-guard test so
  the core `atlaspatch` CLI import graph stays free of them.

## Capabilities

### New Capabilities
- `agent-transport`: the A2A/ADK peer-wiring seam — an `AgentTransport` interface with an
  in-process default and an opt-in A2A implementation that produce byte-identical run
  outputs, emit the `message_flow` telemetry family, and keep CI green with no cloud.

### Modified Capabilities
- `run-telemetry`: reserve-to-concrete — add the typed `message_flow` record family and the
  opt-in `BigQueryTelemetrySink` behind the existing append-only interface.
- `agent-choreography`: replace the "Level-2 message-flow is out of scope" requirement with a
  Level-2 message-flow view rendered from `message_flow`, degrading to Level 1 when absent.

## Impact

- **New code:** `atlas_conductor/transport/` (interface + in-process + A2A implementations),
  a `MessageFlowRecord` and `BigQueryTelemetrySink` in `atlas_conductor/telemetry.py` (or a
  `telemetry_bigquery.py` sibling), a `message_flow.jsonl` family, and
  `atlas_conductor/gui/messageflow.py` plus a Level-2 panel in `gui/app.py`.
- **Modified code:** `run.py` selects the transport (default in-process); `config.py` gains
  transport + telemetry-backend selectors; `scheduler.py`/agent call sites route through the
  transport.
- **Dependencies:** `google-adk`, `a2a-sdk`, `google-cloud-bigquery` added to the
  `orchestrator` extra only, imported behind guards. `pip install atlas-patch` unchanged.
- **Constraints honored:** `atlas_patch/` untouched; telemetry stays metadata-only and
  PHI-free (the new family carries agent ids and message types, no slide pixels/embeddings);
  the deterministic in-process path remains the default and the CI-green target.
