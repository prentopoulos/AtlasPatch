"""Agent-transport seam tests (agent-transport spec, tasks 2.4, 3.5).

Asserts the in-process transport records a ``message_flow`` row per inter-agent handoff,
that selecting a transport does not change what a run computes (the message-flow family is
purely additive over the phase-1–3 families), and that the in-process transport and a
stubbed A2A transport produce identical results (the parity invariant, design D-DIST-6).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import Geometry, RequestedOutput, SlideOutcome
from atlas_conductor.run import run_job
from atlas_conductor.telemetry import InMemoryTelemetrySink
from atlas_conductor.transport import (
    AgentMessage,
    AgentTransport,
    InProcessTransport,
    TransportUnavailableError,
    make_transport,
)

_A2A_INSTALLED = importlib.util.find_spec("a2a") is not None


def _make_cohort(root: Path, stems: list[str]) -> Path:
    cohort = root / "cohort"
    cohort.mkdir(parents=True, exist_ok=True)
    for stem in stems:
        (cohort / f"{stem}.svs").write_bytes(b"fake-wsi")
    return cohort


def _features_config(cohort: Path, out: Path) -> JobConfig:
    return JobConfig(
        input_dir=cohort,
        output_dir=out,
        requested_output=RequestedOutput.FEATURES,
        geometry=Geometry(patch_size=256, target_mag=20),
        encoders=("resnet50",),
    )


def _family_rows_modulo_volatile(sink: InMemoryTelemetrySink) -> dict[str, list[dict]]:
    """Every telemetry family as rows, with run-scoped/volatile fields stripped.

    Dropped: timestamps, the correlation id, the job clock fields, and the run-scoped
    identifiers (``job_id`` and the per-run pseudonymized ``slide_stem``) — the parity
    invariant is about identical *structure and sequence*, not identical run ids.
    """
    from dataclasses import asdict
    from typing import Any

    families: dict[str, list[Any]] = {
        "jobs": list(sink.jobs),
        "slide_stage_outcomes": list(sink.slide_stage_outcomes),
        "validation_results": list(sink.validation_results),
        "agent_events": list(sink.agent_events),
        "message_flow": list(sink.message_flow),
    }
    volatile = {"timestamp", "correlation_id", "started_at", "finished_at", "job_id", "slide_stem"}
    stripped: dict[str, list[dict]] = {}
    for name, records in families.items():
        rows = []
        for record in records:
            row = {k: v for k, v in asdict(record).items() if k not in volatile}
            rows.append(row)
        stripped[name] = rows
    return stripped


def test_make_transport_resolves_in_process_and_rejects_unknown() -> None:
    sink = InMemoryTelemetrySink()
    assert isinstance(make_transport("in-process", sink, "job"), InProcessTransport)
    with pytest.raises(ValueError, match="unknown transport"):
        make_transport("bogus", sink, "job")


@pytest.mark.skipif(_A2A_INSTALLED, reason="a2a-sdk is installed; the extra is present")
def test_a2a_transport_needs_the_orchestrator_extra() -> None:
    # Without the extra, selecting the A2A transport raises a clear, actionable error
    # naming the extra (agent-transport spec) — the default in-process path is unaffected.
    with pytest.raises(TransportUnavailableError, match="orchestrator"):
        make_transport("a2a", InMemoryTelemetrySink(), "job")


@pytest.mark.skipif(not _A2A_INSTALLED, reason="a2a-sdk not installed; loopback path is optional")
def test_a2a_transport_records_flow_without_live_peers() -> None:
    # Optional (skips without the extra so SDK/install issues can't gate CI, task 6.2): the
    # real A2A transport records the message_flow row and tolerates an unreachable peer set
    # (transmission is best-effort; the in-process computation is authoritative, design D8).
    sink = InMemoryTelemetrySink()
    transport = make_transport("a2a", sink, "job")
    try:
        transport.route(
            AgentMessage(from_agent="planner", to_agent="worker", message_type="dispatch")
        )
    finally:
        close = getattr(transport, "close", None)
        if close is not None:
            close()
    assert len(sink.message_flow) == 1
    assert (sink.message_flow[0].from_agent, sink.message_flow[0].to_agent) == ("planner", "worker")


def test_in_process_run_records_message_flow(tmp_path: Path) -> None:
    cohort = _make_cohort(tmp_path, ["slide_a", "slide_b"])
    config = _features_config(cohort, tmp_path / "out")
    sink = InMemoryTelemetrySink()

    run_job(config, sink)

    # The full choreography cycle is recorded: planner→worker on dispatch, then
    # worker→validator on the produced outcome.
    edges = {(m.from_agent, m.to_agent) for m in sink.message_flow}
    assert ("planner", "worker") in edges
    assert ("worker", "validator") in edges
    # Every message names a known type and carries a correlation id.
    assert all(m.message_type for m in sink.message_flow)
    assert all(m.correlation_id for m in sink.message_flow)


def test_message_flow_is_purely_additive(tmp_path: Path) -> None:
    # A run's non-message families are identical whether or not message_flow is recorded:
    # routing only appends to the new family, so outcomes cannot drift (design D-DIST-2).
    cohort = _make_cohort(tmp_path, ["slide_a", "slide_b", "slide_c"])
    config = _features_config(cohort, tmp_path / "out")

    sink = InMemoryTelemetrySink()
    result = run_job(config, sink)

    assert result.count(SlideOutcome.VALID) == 3
    # message_flow was recorded, and it did not disturb the other four families.
    assert sink.message_flow
    assert len(sink.jobs) == 1
    assert {m.from_agent for m in sink.message_flow} <= {
        "planner",
        "worker",
        "validator",
        "recovery",
        "scheduler",
    }


class _StubA2ATransport(AgentTransport):
    """A stand-in for the real A2A transport: records the flow and 'transmits' to a log.

    Stands in for ``atlas_conductor.transport.a2a.A2ATransport`` in CI so the parity
    invariant (design D-DIST-6) is checked without Google ADK / A2A installed or a live peer
    set. It records the same ``message_flow`` family as the in-process transport.
    """

    name = "a2a-stub"

    def __init__(self, telemetry, job_id: str) -> None:  # type: ignore[no-untyped-def]
        super().__init__(telemetry, job_id)
        self.transmitted: list[AgentMessage] = []

    def _deliver(self, message: AgentMessage) -> None:
        self.transmitted.append(message)  # "over the wire" in the real transport


def test_transports_produce_identical_results(tmp_path: Path) -> None:
    # design D-DIST-6: the same job through the in-process transport and a stubbed A2A
    # transport yields identical per-slide results and identical family rows (modulo the
    # volatile timestamp/correlation fields). Both runs use the *same* cohort and output
    # paths — the on-disk output is reset between them — so path-bearing details match and
    # any difference would be the transport's doing.
    import shutil

    cohort = _make_cohort(tmp_path, ["slide_a", "slide_b"])
    out = tmp_path / "out"
    config = _features_config(cohort, out)

    in_proc_sink = InMemoryTelemetrySink()
    in_proc_result = run_job(
        config, in_proc_sink, transport=InProcessTransport(in_proc_sink, "job")
    )

    shutil.rmtree(out)  # reset on-disk state so the second run starts identically

    a2a_sink = InMemoryTelemetrySink()
    stub = _StubA2ATransport(a2a_sink, "job")
    a2a_result = run_job(config, a2a_sink, transport=stub)

    # Identical per-slide outcomes (RunResult carries raw stems, identical across runs).
    assert [(s.slide_stem, s.outcome) for s in in_proc_result.slides] == [
        (s.slide_stem, s.outcome) for s in a2a_result.slides
    ]
    # The A2A stub actually transmitted the messages it recorded.
    assert len(stub.transmitted) == len(a2a_sink.message_flow)
    # Identical family rows modulo the volatile run-scoped fields.
    in_proc_rows = _family_rows_modulo_volatile(in_proc_sink)
    a2a_rows = _family_rows_modulo_volatile(a2a_sink)
    for family in ("slide_stage_outcomes", "validation_results", "agent_events", "message_flow"):
        assert in_proc_rows[family] == a2a_rows[family], family
