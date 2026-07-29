"""Loopback A2A integration test (agent-transport spec, design D-DIST-6).

Stands up the four agent peers as real A2A servers on loopback, runs a job through the A2A
transport, and asserts (a) the handoffs are delivered **over the wire** — a peer's server-side
executor actually receives them — and (b) the run's per-slide outcome is identical to the
in-process transport (the parity invariant). Skips when ``a2a-sdk`` is not installed, so
SDK/install issues can never gate CI (task 6.2); the CI-green parity proof uses a stub.
"""

from __future__ import annotations

import asyncio
import importlib.util
import shutil
import socket
import threading
import time
from pathlib import Path

import pytest

from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import Geometry, RequestedOutput
from atlas_conductor.run import run_job
from atlas_conductor.telemetry import InMemoryTelemetrySink
from atlas_conductor.transport import InProcessTransport, make_transport

_A2A_INSTALLED = importlib.util.find_spec("a2a") is not None

pytestmark = pytest.mark.skipif(
    not _A2A_INSTALLED, reason="a2a-sdk not installed; the loopback A2A path is optional"
)


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


def _wait_for_port(host: str, port: int, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.5)
            try:
                sock.connect((host, port))
                return True
            except OSError:
                time.sleep(0.1)
    return False


class _PeerSet:
    """Run the four A2A peer servers in a background thread for the duration of a test."""

    def __init__(self, on_receive) -> None:  # type: ignore[no-untyped-def]
        from atlas_conductor.transport import a2a as a2a_mod

        self._a2a = a2a_mod
        self._servers = a2a_mod.build_servers(on_receive=on_receive)
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(asyncio.gather(*(server.serve() for server in self._servers)))

    def __enter__(self) -> _PeerSet:
        self._thread.start()
        for port in self._a2a.AGENT_PORTS.values():
            assert _wait_for_port("127.0.0.1", port), f"peer on port {port} did not start"
        return self

    def __exit__(self, *exc) -> None:  # type: ignore[no-untyped-def]
        for server in self._servers:
            server.should_exit = True
        self._thread.join(timeout=10)


def test_a2a_loopback_delivers_over_the_wire_and_matches_in_process(tmp_path: Path) -> None:
    received: list[tuple[str, str]] = []

    cohort = _make_cohort(tmp_path, ["slide_a", "slide_b"])
    out = tmp_path / "out"
    config = _features_config(cohort, out)

    # In-process baseline.
    base_sink = InMemoryTelemetrySink()
    base = run_job(config, base_sink, transport=InProcessTransport(base_sink, "job"))
    shutil.rmtree(out)  # reset on-disk state so the A2A run starts identically

    # Run through the live loopback peer set.
    with _PeerSet(on_receive=lambda agent, text: received.append((agent, text))):
        a2a_sink = InMemoryTelemetrySink()
        transport = make_transport("a2a", a2a_sink, "job")
        try:
            a2a_result = run_job(config, a2a_sink, transport=transport)
        finally:
            close = getattr(transport, "close", None)
            if close is not None:
                close()

    # Parity: identical per-slide outcomes across transports (design D-DIST-6).
    assert [(s.slide_stem, s.outcome) for s in base.slides] == [
        (s.slide_stem, s.outcome) for s in a2a_result.slides
    ]
    # The transport recorded the message_flow family.
    assert a2a_sink.message_flow
    # Genuine over-the-wire delivery: peer servers actually received the handoffs.
    assert received, "no peer received a handoff over the wire"
    receiving_agents = {agent for agent, _text in received}
    assert receiving_agents & {"worker", "validator", "recovery", "planner"}
