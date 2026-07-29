## Context

Phase 1 built the operational core as four plain in-process components (planner, worker,
validator, recovery) coordinated by `atlas_conductor/run.py`, with a deterministic scheduler
governor and a typed, append-only, metadata-only telemetry sink (`telemetry.py`: families
`jobs`, `slide_stage_outcomes`, `validation_results`, `agent_events`; `JsonlTelemetrySink`
default). Phase 2 wrapped the sink in a PHI-free write gate. Phase 3 added a read-only
Streamlit GUI that tails those families, including a Level-1 choreography view
(`gui/choreography.py`) that derives lit/dim agent state from `agent_events` alone.

Two seams were deliberately reserved for this phase:
- **D8** — the four agents are to become **A2A peers on Google ADK + A2A**, with the
  scheduler staying an in-process governor. The justification is explicit: the deterministic
  core (D11) does *not* need A2A for correctness; the protocol earns its weight as an
  **observability payoff** — the real inter-agent messages are exactly what the GUI Level-2
  message-flow view renders — and is therefore wired **last** (Run C), behind the optional
  `orchestrator` extra.
- The **run-telemetry** spec reserved a **BigQuery backend** "added in phase 4 behind the
  same interface without changing what any agent records," and the **agent-choreography**
  spec has a standing "Level-2 message-flow is out of scope" requirement pending this wiring.

Hard constraints from PROJECT.md carry in: `atlas_patch/` is untouched; telemetry stays
metadata-only and PHI-free; heavy deps live behind `atlas-patch[orchestrator]` so
`pip install atlas-patch` and the core `atlaspatch` CLI are unchanged; and the in-process
path must stay the **default and the green-in-CI target** with no cloud credentials.

## Goals / Non-Goals

**Goals:**
- An `AgentTransport` seam letting the run façade route the four agents through either an
  in-process transport (default, identical outputs) or an A2A/ADK transport (opt-in), chosen
  the same way real/fake adapters already are.
- A typed `message_flow` telemetry family capturing `(from_agent, to_agent, message_type,
  correlation, slide_stem?, stage?)`, emitted by **both** transports so the Level-2 view and
  its AppTest proof never require a live A2A network.
- An opt-in `BigQueryTelemetrySink` behind the existing append-only interface; local JSONL
  stays the default.
- A GUI Level-2 message-flow panel: edges between agent nodes pulsing on message recency,
  degrading to Level-1-only when a run has no `message_flow` rows.
- CI green end-to-end on the in-process transport + JSONL backend against the fake adapter;
  the ADK/A2A/BigQuery code paths import-guarded and unit-tested with fakes.

**Non-Goals:**
- Making A2A or BigQuery mandatory, or changing any run's outputs when they are enabled — the
  transport is an observability/scale layer, not a behavior change (D8).
- A live multi-host deployment topology, service discovery, or auth hardening for A2A servers
  beyond a localhost/loopback peer set sufficient to demonstrate real messages.
- Any new telemetry field capable of holding pixels, masks, or embeddings (D9 invariant).
- Touching `atlas_patch/`, the scheduler's governor logic, or the four families' shapes.
- The phase-5+ data-lineage, learned classifier, or compliance dossier work.

## Decisions

### D-DIST-1 — An `AgentTransport` seam, mirroring the real/fake adapter pattern
The four agents' interactions are routed through a new `AgentTransport` interface in
`atlas_conductor/transport/`, with `InProcessTransport` (default) and `A2ATransport`
(opt-in). `run.py` selects it exactly as `make_adapter` selects real/fake today; the
in-process transport calls the components directly, so its outputs are byte-identical to the
phase-1–3 path. Rationale: the repo already proved this pattern (execution-dispatch's two
adapters sharing one interface) — reusing it keeps A2A a swappable transport, not a rewrite,
and makes "core runs without A2A" structural.
- *Alternative considered:* thread ADK through the agents directly. Rejected — couples every
  component to the message bus, breaks the identical-outputs invariant, and makes CI depend
  on cloud SDKs.

### D-DIST-2 — Both transports emit the `message_flow` family; the view reads telemetry, not the wire
The Level-2 view renders from a persisted `message_flow` telemetry family, not from a live
A2A socket. Every routed interaction — in-process or A2A — records one `MessageFlowRecord`.
Rationale: the GUI is a read-only tailer (D-GUI-1); reading a persisted family keeps it
decoupled from the transport lifecycle and lets the AppTest assert real edges from an
in-process fake run in CI. The A2A transport additionally sends the message over the wire; the
telemetry row is the same shape either way, so "real messages" and "test messages" render
identically — the difference is only whether a socket was involved.
- *Alternative considered:* have the GUI subscribe to A2A directly. Rejected — puts a live,
  cloud-dependent, write-capable client in the read-only surface and makes the panel
  untestable without a running peer set.

### D-DIST-3 — `MessageFlowRecord` is a fifth typed family, metadata-only
`message_flow` is a new frozen dataclass `(job_id, from_agent, to_agent, message_type,
correlation_id, slide_stem?, stage?, timestamp)` added to `telemetry.py`, with a
`record_message_flow` method on `TelemetrySink` and a `message_flow.jsonl` file on
`JsonlTelemetrySink`. It carries only agent identifiers, an enum message type, and a
correlation id — no array field — so the D9 metadata-only invariant holds by type, and the
phase-2 PHI gate covers `slide_stem` through the same pseudonymization path as the other
families. Rationale: a distinct family keeps the four existing shapes frozen (D17 caveat) and
gives the Level-2 view a clean read target.
- *Alternative considered:* overload `agent_events` with `to_agent`. Rejected — mutates a
  load-bearing shape every earlier renderer reads, for a distinct concern (edges vs. states).

### D-DIST-4 — `BigQueryTelemetrySink` behind the same interface, opt-in, fake-tested
The BigQuery backend implements the same `TelemetrySink` ABC, mapping each family to a table
and each record to a row insert. It is selected only when explicitly configured
(`telemetry.backend: bigquery` + dataset), imports `google-cloud-bigquery` behind a guard,
and is unit-tested against a fake client that captures inserts — asserting the row shape
matches the JSONL rows without a live GCP connection. Rationale: satisfies the run-telemetry
spec's "same records through the same interface" verbatim, and keeps the credential-free
JSONL default as the CI backend.
- *Alternative considered:* a streaming/BigQuery-only telemetry path. Rejected — would make
  cloud the default and violate "run does not require any cloud credentials."

### D-DIST-5 — Heavy deps in the `orchestrator` extra, guarded, enforced by the import-guard test
`google-adk`, `a2a-sdk`, and `google-cloud-bigquery` are added to the `orchestrator` extra.
Each is imported only inside its own module (`transport/a2a.py`, the BigQuery sink), never
from `cli.py`, `run.py`, `telemetry.py`'s core, or the in-process transport. The existing CI
import-guard test (added for the GUI's streamlit guard) is extended to assert the core CLI
import graph pulls in none of them. Rationale: preserves the PROJECT.md constraint that
`pip install atlas-patch` is unchanged and the base CLI has no cloud footprint.
- *Alternative considered:* a separate `distribution` extra. Rejected — the phase-1 pyproject
  note already reserves these three deps for the single `orchestrator` extra; splitting adds
  install surface for no isolation benefit since imports are already guarded per-module.

### D-DIST-6 — A2A peer set is loopback, launched by a thin runner; identical run outputs verified
`A2ATransport` exposes each of the four agents as an ADK agent behind an A2A server on
loopback, with the scheduler as the in-process client that routes tasks to peers. A thin
runner (a `atlaspatch-conduct` subcommand or documented module entry) starts the peer set for
a demo/real run. A parity test runs the same job through `InProcessTransport` and a stubbed
`A2ATransport` and asserts identical per-slide `RunResult` and identical family rows modulo
timestamps/correlation ids. Rationale: makes D8's "would produce identical outputs" a checked
invariant, and keeps the A2A surface a localhost demonstration (Non-Goal: no multi-host
topology) matched to the phase's observability purpose.
- *Alternative considered:* in-memory ADK runner with no sockets. Kept as the CI stub, but the
  loopback server path is retained so the demo shows genuine over-the-wire messages (the whole
  point of D8's justification).

### D-DIST-7 — Each ADK peer is a *deterministic custom `BaseAgent`*, never an `LlmAgent` (as-built)
The four peers are implemented as custom `google.adk.agents.BaseAgent` subclasses whose
`_run_async_impl` yields a single acknowledgement event — **not** `LlmAgent` — so an ADK peer
performs **no model inference**. Each is exposed over A2A with ADK's `to_a2a()`, and the
transport reaches peers with ADK's `RemoteA2aAgent` client over an in-memory `Runner`
(`transport/a2a.py`). Rationale: D8 mandates "Google ADK + A2A", but ADK is LLM-oriented and
the conductor's load-bearing invariant is a *deterministic* core with no clinical/agentic
reasoning (keeping the layer out of SaMD scope). A custom `BaseAgent` reconciles the two — the
agents are genuinely ADK agents wired as real A2A peers, yet the deterministic-core invariant
holds unchanged over the wire. Verified end-to-end against `google-adk` 2.5.0: the loopback
integration test stands up the four ADK peers and confirms each peer's `_run_async_impl` runs
on a handoff received over A2A, with per-slide `RunResult` parity to the in-process transport.
- *Alternative considered:* wrap each agent as an `LlmAgent` with a trivial prompt. Rejected —
  introduces a model dependency and non-determinism into a core whose whole premise is that it
  does no reasoning; it would also make runs require model credentials.
- *Alternative considered (and initially built):* the raw `a2a-sdk` `AgentExecutor`/FastAPI
  server directly, without ADK. Rejected — D8 specifies ADK, and ADK's `to_a2a()` /
  `RemoteA2aAgent` are the idiomatic path; the direct-`a2a-sdk` build was reworked onto ADK.
- *Caveat:* ADK's A2A support is flagged `[EXPERIMENTAL]` by Google (functional, API subject to
  change). It is confined to the opt-in `transport/a2a.py`; the deterministic core, the default
  in-process transport, and CI never import it, so churn there cannot regress the core.

## Risks / Trade-offs

- **ADK/A2A SDK churn or install weight on the dev box** → the extra is opt-in and every heavy
  import is guarded; CI and the default run never import them, so SDK breakage cannot regress
  the core. The loopback peer set is exercised in a marked/optional test, not the default suite.
- **Two transports drifting** (in-process vs A2A produce different outputs) → the D-DIST-6
  parity test pins identical `RunResult` + family rows; the in-process transport remains the
  source of truth and the default.
- **BigQuery row-shape drift from JSONL** → the fake-client test asserts the BigQuery insert
  dict equals the JSONL row for each family, so the "same records" guarantee is checked, not
  assumed.
- **Level-2 panel emptiness confusing** (a plain in-process run with the transport off has no
  edges) → the panel degrades explicitly to Level-1-only with a "no message flow recorded for
  this run" state rather than rendering a broken graph.
- **PHI leak via the new family** → `message_flow.slide_stem` flows through the same PhiSafeSink
  pseudonymization as every other family; the metadata-only-by-type test is extended to the new
  record so no array field can be added.

## Migration Plan

Additive and default-off. No existing run, telemetry file, or GUI panel changes when the
transport and backend are left at their defaults (`in-process`, `jsonl`). Enabling A2A or
BigQuery is a config opt-in that requires the `orchestrator` extra; disabling reverts to the
identical core path. No data migration — `message_flow.jsonl` is a new file that older runs
simply lack, which the Level-2 view already handles via its degrade-to-Level-1 state.

## Open Questions

- Exact ADK/A2A SDK package names/versions to pin (`google-adk`, `a2a-sdk`) — resolve against
  the current published packages at implementation time via the pinned lower bounds.
- Whether the loopback peer runner ships as a `atlaspatch-conduct a2a-demo` subcommand or a
  documented `python -m atlas_conductor.transport.a2a` entry — decide during apply; both keep
  the import guarded.
