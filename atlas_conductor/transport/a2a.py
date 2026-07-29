"""The A2A agent transport — the opt-in, over-the-wire choreography on Google ADK (D-DIST-5/6).

This module wires the four logical agents (planner, worker, validator, recovery) as
**Google ADK** agents exposed as **Agent2Agent (A2A)** peers. It is imported **only** through
``make_transport("a2a")`` and never from the core CLI, the run façade, or the in-process
transport, so the base ``atlaspatch`` import graph stays cloud-free (design D-DIST-5). The
heavy dependencies (``google-adk`` and its A2A/HTTP stack) live in the
``atlas-patch[orchestrator]`` extra; importing this module without them raises
``ModuleNotFoundError``, which ``make_transport`` turns into a clean
:class:`~atlas_conductor.transport.TransportUnavailableError`.

Design (D8): the four agents run as ADK agents exposed over A2A via ADK's ``to_a2a()``, and
the transport reaches them with ADK's ``RemoteA2aAgent`` client. Crucially each peer is a
**custom deterministic** ADK ``BaseAgent`` — *not* an ``LlmAgent`` — so it performs no model
inference: the conductor's deterministic-core invariant (no clinical/agentic reasoning) holds
even when the agents run as ADK A2A peers. The scheduler remains the in-process governor and
authoritative computation (design D-DIST-6); a peer's only job is to *receive* a handoff,
making the choreography genuinely over-the-wire, and acknowledge it. The transport records the
same metadata-only ``message_flow`` family as the in-process transport, so the GUI Level-2
view renders identical rows whether or not a socket was involved.

Scope (design Non-Goals): a localhost/loopback peer set sufficient to demonstrate real
messages — no multi-host topology, service discovery, or auth hardening. This path is
exercised by an opt-in integration test that skips when the extra is not installed
(task 6.2); the CI-green parity proof uses a stubbed transport instead (task 3.5).

ADK's A2A support is marked *experimental* by Google (functional, subject to change); its
``[EXPERIMENTAL]`` warnings are silenced below since this module opts into that surface.
"""

from __future__ import annotations

import asyncio
import logging
import warnings
from collections.abc import AsyncGenerator, Callable, Mapping

import uvicorn
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.remote_a2a_agent import AGENT_CARD_WELL_KNOWN_PATH, RemoteA2aAgent
from google.adk.events import Event
from google.adk.runners import InMemoryRunner
from google.genai import types as genai_types

from atlas_conductor.agents import Agent
from atlas_conductor.telemetry import TelemetrySink
from atlas_conductor.transport import AgentMessage, AgentTransport

# ADK's A2A implementation is functional but flagged experimental; silence the noise on the
# opt-in path (this filter only takes effect once this module is imported via make_transport).
warnings.filterwarnings("ignore", message=r".*\[EXPERIMENTAL\].*")

logger = logging.getLogger(__name__)

# The four logical agents that run as ADK/A2A peers. The scheduler stays in-process (D8).
PEER_AGENTS: tuple[str, ...] = (
    Agent.PLANNER.value,
    Agent.WORKER.value,
    Agent.VALIDATOR.value,
    Agent.RECOVERY.value,
)

# Loopback port per peer — a fixed, contiguous block on 127.0.0.1 (Non-Goal: no discovery).
_BASE_PORT = 41240
AGENT_PORTS: dict[str, int] = {agent: _BASE_PORT + i for i, agent in enumerate(PEER_AGENTS)}

# Optional observability hook: called on the server with (agent, received_text) each time a
# peer receives a handoff. Keyed by agent name in a module registry because an ADK ``BaseAgent``
# is a pydantic model that does not take arbitrary instance attributes. Used by the loopback
# runner to log receipts and by the integration test to prove genuine over-the-wire delivery.
OnReceive = Callable[[str, str], None]
_RECEIVE_HOOKS: dict[str, OnReceive] = {}


def agent_url(agent: str, host: str = "127.0.0.1") -> str:
    """The base URL a peer agent's A2A server listens on."""
    return f"http://{host}:{AGENT_PORTS[agent]}"


class _HandoffAgent(BaseAgent):
    """A deterministic ADK agent (custom ``BaseAgent``, no LLM) that acknowledges a handoff.

    Subclassing ``BaseAgent`` rather than ``LlmAgent`` means the peer does no model inference,
    so the deterministic-core invariant holds while the agents run as ADK A2A peers (design
    D8/D-DIST-6). It fires the optional receive hook (proving the handoff arrived) and yields a
    single acknowledgement event.
    """

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        hook = _RECEIVE_HOOKS.get(self.name)
        if hook is not None:
            hook(self.name, _incoming_text(ctx))
        yield Event(
            author=self.name,
            content=genai_types.Content(
                role="model", parts=[genai_types.Part(text=f"{self.name} acknowledged handoff")]
            ),
        )


def _incoming_text(ctx: InvocationContext) -> str:
    """Best-effort extraction of the received handoff text (observability only)."""
    try:
        user_content = getattr(ctx, "user_content", None)
        if user_content is not None and user_content.parts:
            return user_content.parts[0].text or ""
    except Exception:  # pragma: no cover - the hook must never break the peer
        pass
    return ""


def build_servers(host: str = "127.0.0.1", on_receive: OnReceive | None = None) -> list:
    """One configured (unstarted) ``uvicorn.Server`` per peer agent on its loopback port.

    Each server hosts an ADK ``_HandoffAgent`` exposed over A2A via ADK's ``to_a2a()``. Shared
    by :func:`serve_peer_set` (the demo runner) and the loopback integration test so both stand
    up the peers the same way.
    """
    _RECEIVE_HOOKS.clear()
    servers = []
    for agent, port in AGENT_PORTS.items():
        if on_receive is not None:
            _RECEIVE_HOOKS[agent] = on_receive
        app = to_a2a(
            _HandoffAgent(
                name=agent, description=f"AtlasPatch Conductor {agent} agent (A2A peer)."
            ),
            host=host,
            port=port,
        )
        servers.append(
            uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))
        )
    return servers


class A2ATransport(AgentTransport):
    """Route handoffs over A2A: record the ``message_flow`` row *and* transmit to the peer.

    Recording is inherited from :class:`AgentTransport`; only ``_deliver`` is overridden to
    send the handoff to the target agent's ADK peer via a reused ``RemoteA2aAgent`` runner.
    Transmission is best-effort — the in-process computation is authoritative (design D8), so a
    peer that is unreachable logs a warning and the run proceeds, still with the flow recorded.
    """

    name = "a2a"

    def __init__(
        self,
        telemetry: TelemetrySink,
        job_id: str,
        host: str = "127.0.0.1",
        peers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(telemetry, job_id)
        self._host = host
        self._peers = (
            dict(peers) if peers is not None else {a: agent_url(a, host) for a in PEER_AGENTS}
        )
        self._loop = asyncio.new_event_loop()
        # One ADK RemoteA2aAgent + in-memory runner per peer, reused across the run.
        self._runners: dict[str, InMemoryRunner] = {}
        for agent, url in self._peers.items():
            remote = RemoteA2aAgent(
                name=f"peer_{agent}",
                description=f"Remote {agent} A2A peer.",
                agent_card=f"{url}{AGENT_CARD_WELL_KNOWN_PATH}",
                use_legacy=False,
            )
            self._runners[agent] = InMemoryRunner(agent=remote, app_name=f"conductor-{agent}")

    def _deliver(self, message: AgentMessage) -> None:
        runner = self._runners.get(message.to_agent)
        if runner is None:
            return  # e.g. the scheduler is not a peer; nothing to transmit
        try:
            self._loop.run_until_complete(self._send(runner, message))
        except Exception as exc:  # pragma: no cover - network/peer errors must not fail a run
            logger.warning("A2A transmit to %s failed: %s", message.to_agent, exc)

    async def _send(self, runner: InMemoryRunner, message: AgentMessage) -> None:
        session = await runner.session_service.create_session(
            app_name=runner.app_name, user_id="conductor"
        )
        content = genai_types.Content(
            role="user", parts=[genai_types.Part(text=_handoff_text(message))]
        )
        async for _event in runner.run_async(
            user_id="conductor", session_id=session.id, new_message=content
        ):
            pass  # drain the peer's acknowledgement stream

    def close(self) -> None:
        """Release the transport's event loop (call after a run)."""
        self._loop.close()


def _handoff_text(message: AgentMessage) -> str:
    text = f"{message.message_type} handoff {message.from_agent}->{message.to_agent}"
    if message.slide_stem:
        text += f" slide={message.slide_stem}"
    if message.stage:
        text += f" stage={message.stage}"
    return text


async def serve_peer_set(host: str = "127.0.0.1", on_receive: OnReceive | None = None) -> None:
    """Start every peer agent's ADK/A2A server on loopback and serve until interrupted."""
    servers = build_servers(host, on_receive)
    logger.info("serving %d ADK/A2A peers on %s: %s", len(servers), host, AGENT_PORTS)
    await asyncio.gather(*(server.serve() for server in servers))


def main() -> None:  # pragma: no cover - the loopback runner (design D-DIST-6, task 3.4)
    """Start the loopback peer set. Run a job against it with ``transport: a2a`` in its config.

    Usage:
        python -m atlas_conductor.transport.a2a         # terminal 1: start the four peers
        atlaspatch-conduct run job.yaml                 # terminal 2: run with transport: a2a
    """
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve_peer_set())


if __name__ == "__main__":  # pragma: no cover
    main()
