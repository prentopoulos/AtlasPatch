"""The agent-transport seam (agent-transport spec, design D-DIST-1/2).

The four logical agents (planner, worker, validator, recovery) interact along four
handoffs — planner→worker (dispatch), worker→validator (outcome), validator→recovery
(classify), recovery→planner (apply). An :class:`AgentTransport` *routes* each handoff,
recording one metadata-only ``message_flow`` telemetry row per interaction. The scheduler
stays the in-process governor and routes tasks through the selected transport (design D8).

Two implementations share this one interface, chosen the same way the real/fake execution
adapter is (``make_transport`` mirrors ``make_adapter``):

* :class:`InProcessTransport` — the default. It records the flow and returns; the caller has
  already invoked the target component directly, so run outputs are byte-identical to the
  phase-1–3 path. The routing is pure observation.
* ``A2ATransport`` (``atlas_conductor.transport.a2a``, opt-in) — records the same flow *and*
  transmits the message to the peer's A2A server, so the choreography is genuinely
  over-the-wire. It imports Google ADK / A2A only inside its own module, behind the
  ``orchestrator`` extra, so the core CLI import graph stays cloud-free.

Because routing only appends to the new ``message_flow`` family — never to ``agent_events``,
the outcomes, the validations, or the job row, and never to :class:`RunResult` — selecting a
transport cannot change what a run computes.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from atlas_conductor.telemetry import MessageFlowRecord, TelemetrySink


class MessageType(str, Enum):
    """The declarative intent of an inter-agent message (design D-DIST-2)."""

    DISPATCH = "dispatch"  # planner -> worker: run this task
    OUTCOME = "outcome"  # worker -> validator: here is the raw outcome to verify
    CLASSIFY = "classify"  # validator -> recovery: this verdict is invalid, classify it
    APPLY = "apply"  # recovery -> planner: apply this recovery proposal


@dataclass(frozen=True)
class AgentMessage:
    """One inter-agent interaction to route. Carries only declarative metadata."""

    from_agent: str
    to_agent: str
    message_type: str  # a MessageType value
    slide_stem: str | None = None
    stage: str | None = None
    correlation_id: str = ""


class AgentTransport(ABC):
    """Route inter-agent messages, recording each as a ``message_flow`` telemetry row."""

    name: str = "agent-transport"

    def __init__(self, telemetry: TelemetrySink, job_id: str) -> None:
        self._telemetry = telemetry
        self._job_id = job_id

    def route(self, message: AgentMessage) -> None:
        """Record the interaction, then deliver it via the concrete transport."""
        correlation_id = message.correlation_id or uuid.uuid4().hex
        self._telemetry.record_message_flow(
            MessageFlowRecord(
                job_id=self._job_id,
                from_agent=message.from_agent,
                to_agent=message.to_agent,
                message_type=message.message_type,
                correlation_id=correlation_id,
                slide_stem=message.slide_stem,
                stage=message.stage,
            )
        )
        self._deliver(message)

    @abstractmethod
    def _deliver(self, message: AgentMessage) -> None:
        """Transmit the message (a no-op for the in-process transport)."""
        raise NotImplementedError


class InProcessTransport(AgentTransport):
    """The default transport: record the flow only; the caller runs the target in-process."""

    name = "in-process"

    def _deliver(self, message: AgentMessage) -> None:
        # In-process: the scheduler has already invoked the target component directly, so
        # there is nothing to transmit — routing is pure observation. This keeps run outputs
        # byte-identical to a run with no transport (design D-DIST-2).
        return


def make_transport(name: str, telemetry: TelemetrySink, job_id: str) -> AgentTransport:
    """Resolve a transport by name, mirroring ``make_adapter``.

    ``in-process`` (default) needs no cloud and no peers; ``a2a`` wires the agents as
    Google ADK / A2A peers on loopback and requires the ``orchestrator`` extra.
    """
    if name == "in-process":
        return InProcessTransport(telemetry, job_id)
    if name == "a2a":
        try:
            from atlas_conductor.transport.a2a import A2ATransport
        except ModuleNotFoundError as exc:  # pragma: no cover - exercised only without the extra
            raise TransportUnavailableError(
                "the A2A transport requires the orchestrator extra (Google ADK + A2A); "
                "install it: pip install 'atlas-patch[orchestrator]'"
            ) from exc
        return A2ATransport(telemetry, job_id)
    raise ValueError(f"unknown transport {name!r}; choose 'in-process' or 'a2a'")


class TransportUnavailableError(RuntimeError):
    """The selected transport's optional dependencies are not installed."""
