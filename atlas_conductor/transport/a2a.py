"""The A2A agent transport — the opt-in, over-the-wire choreography (design D-DIST-5/6).

This module wires the four logical agents (planner, worker, validator, recovery) as
Agent2Agent (A2A) peers on Google's protocol SDK. It is imported **only** through
``make_transport("a2a")`` and never from the core CLI, the run façade, or the in-process
transport, so the base ``atlaspatch`` import graph stays cloud-free (design D-DIST-5). The
heavy dependencies (``a2a-sdk`` and its ``httpx`` / ``uvicorn`` / ``fastapi`` stack) live in
the ``atlas-patch[orchestrator]`` extra; importing this module without them raises
``ModuleNotFoundError``, which ``make_transport`` turns into a clean
:class:`~atlas_conductor.transport.TransportUnavailableError`.

Why it exists (design D8): the deterministic core does **not** need A2A for correctness —
the in-process transport already produces identical outputs. The A2A transport earns its
weight as *watchable choreography*: it records the same ``message_flow`` family as the
in-process transport **and** transmits each handoff to the target agent's peer server, so the
GUI Level-2 view renders genuine over-the-wire messages. The scheduler remains the in-process
governor and authoritative computation (design D-DIST-6); the peers acknowledge the handoffs.

Scope (design Non-Goals): a localhost/loopback peer set sufficient to demonstrate real
messages — no multi-host topology, service discovery, or auth hardening. This path is
exercised by an opt-in integration test that skips when the extra is not installed
(task 6.2); the CI-green parity proof uses a stubbed transport instead (task 3.5).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable, Mapping

import httpx
import uvicorn
from a2a.client import ClientConfig, ClientFactory
from a2a.client.client_factory import TransportProtocol
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_rest_routes,
)
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Message,
    Part,
    Role,
    SendMessageConfiguration,
    SendMessageRequest,
)
from fastapi import FastAPI

from atlas_conductor.agents import Agent
from atlas_conductor.telemetry import TelemetrySink
from atlas_conductor.transport import AgentMessage, AgentTransport

logger = logging.getLogger(__name__)

# The four logical agents that run as A2A peers. The scheduler stays in-process (design D8).
PEER_AGENTS: tuple[str, ...] = (
    Agent.PLANNER.value,
    Agent.WORKER.value,
    Agent.VALIDATOR.value,
    Agent.RECOVERY.value,
)

# Loopback port per peer — a fixed, contiguous block on 127.0.0.1 (Non-Goal: no discovery).
_BASE_PORT = 41240
AGENT_PORTS: dict[str, int] = {agent: _BASE_PORT + i for i, agent in enumerate(PEER_AGENTS)}

_REST_PREFIX = "/a2a/rest"


def agent_url(agent: str, host: str = "127.0.0.1") -> str:
    """The base URL a peer agent's A2A server listens on."""
    return f"http://{host}:{AGENT_PORTS[agent]}"


def build_agent_card(agent: str, host: str = "127.0.0.1") -> AgentCard:
    """The A2A AgentCard advertised by (and used to reach) one peer agent.

    Built deterministically from the agent name and host so both the server and the client
    describe the same peer without a discovery round-trip (Non-Goal: no service discovery).
    """
    base = agent_url(agent, host)
    return AgentCard(
        name=f"atlas-conductor-{agent}",
        description=f"AtlasPatch Conductor {agent} agent (A2A peer).",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=[
            AgentSkill(
                id=f"{agent}-handoff",
                name=f"{agent} handoff",
                description=f"Receive an inter-agent handoff addressed to the {agent} agent.",
                tags=["conductor", "choreography"],
            )
        ],
        supported_interfaces=[
            AgentInterface(
                protocol_binding="HTTP+JSON",
                protocol_version="1.0",
                url=f"{base}{_REST_PREFIX}",
            )
        ],
    )


# Optional observability hook: called on the server with (agent, received_text) each time a
# peer receives a handoff. Used by the loopback runner to log receipts and by the integration
# test to prove genuine over-the-wire delivery.
OnReceive = Callable[[str, str], None]


class _HandoffExecutor(AgentExecutor):
    """A peer agent's server-side executor: acknowledge a received handoff.

    The scheduler is authoritative (design D-DIST-6), so a peer's job is only to *receive*
    the handoff message — making the choreography genuinely over-the-wire — and complete. It
    performs no pipeline work and reads no slide data.
    """

    def __init__(self, agent: str, on_receive: OnReceive | None = None) -> None:
        self._agent = agent
        self._on_receive = on_receive

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id
        context_id = context.context_id
        if not task_id or not context_id:
            return
        received = context.get_user_input()
        logger.info("[%s] received handoff: %s", self._agent, received)
        if self._on_receive is not None:
            self._on_receive(self._agent, received)
        updater = TaskUpdater(event_queue=event_queue, task_id=task_id, context_id=context_id)
        await updater.add_artifact(
            parts=[Part(text=f"{self._agent} acknowledged handoff")],
            name="ack",
            last_chunk=True,
        )
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        return


def create_agent_app(
    agent: str, host: str = "127.0.0.1", on_receive: OnReceive | None = None
) -> FastAPI:
    """Build the FastAPI app exposing one peer agent over A2A HTTP+JSON."""
    card = build_agent_card(agent, host)
    handler = DefaultRequestHandler(
        agent_executor=_HandoffExecutor(agent, on_receive),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    app = FastAPI()
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(agent_card=card),
        rest_routes=create_rest_routes(request_handler=handler, path_prefix=_REST_PREFIX),
    )
    return app


def build_servers(
    host: str = "127.0.0.1", on_receive: OnReceive | None = None
) -> list[uvicorn.Server]:
    """One configured (unstarted) ``uvicorn.Server`` per peer agent on its loopback port.

    Shared by :func:`serve_peer_set` (the demo runner) and the loopback integration test so
    both stand up the peers the same way.
    """
    return [
        uvicorn.Server(
            uvicorn.Config(
                create_agent_app(agent, host, on_receive), host=host, port=port, log_level="warning"
            )
        )
        for agent, port in AGENT_PORTS.items()
    ]


class A2ATransport(AgentTransport):
    """Route handoffs over A2A: record the ``message_flow`` row *and* transmit to the peer.

    Recording is inherited from :class:`AgentTransport`; only ``_deliver`` is overridden to
    send the message to the target agent's peer server. Transmission is best-effort — the
    in-process computation is authoritative (design D8), so a peer that is unreachable logs a
    warning and the run proceeds, still with the flow recorded.
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
        self._httpx = httpx.AsyncClient()
        self._factory = ClientFactory(
            config=ClientConfig(
                httpx_client=self._httpx,
                supported_protocol_bindings=[TransportProtocol.HTTP_JSON],
            )
        )

    def _deliver(self, message: AgentMessage) -> None:
        if message.to_agent not in self._peers:
            return  # e.g. the scheduler is not a peer; nothing to transmit
        try:
            self._loop.run_until_complete(self._send(message))
        except Exception as exc:  # pragma: no cover - network/peer errors must not fail a run
            logger.warning("A2A transmit to %s failed: %s", message.to_agent, exc)

    async def _send(self, message: AgentMessage) -> None:
        card = build_agent_card(message.to_agent, self._host)
        client = self._factory.create(card)
        text = (
            f"{message.message_type} handoff {message.from_agent}->{message.to_agent}"
            + (f" slide={message.slide_stem}" if message.slide_stem else "")
            + (f" stage={message.stage}" if message.stage else "")
        )
        request = SendMessageRequest(
            message=Message(
                role=Role.ROLE_USER,
                message_id=uuid.uuid4().hex,
                parts=[Part(text=text)],
            ),
            configuration=SendMessageConfiguration(),
        )
        async for _event in client.send_message(request=request):
            pass  # drain the peer's acknowledgement stream

    def close(self) -> None:
        """Release the httpx client and event loop (call after a run)."""
        try:
            self._loop.run_until_complete(self._httpx.aclose())
        finally:
            self._loop.close()


async def serve_peer_set(host: str = "127.0.0.1", on_receive: OnReceive | None = None) -> None:
    """Start every peer agent's A2A server on loopback and serve until interrupted."""
    servers = build_servers(host, on_receive)
    logger.info("serving %d A2A peers on %s: %s", len(servers), host, AGENT_PORTS)
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
