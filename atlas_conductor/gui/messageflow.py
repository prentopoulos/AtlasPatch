"""The Level-2 message-flow state (agent-choreography spec, design D-DIST-2).

Where the Level-1 choreography view (:mod:`atlas_conductor.gui.choreography`) shows which
agents are *active*, the Level-2 view shows the *edges* between them: the directed inter-agent
messages a run recorded in the ``message_flow`` family, with the most recent edge emphasized
(pulsing). Everything here is *derived* from the persisted ``message_flow`` rows — the GUI
stays a read-only tailer (design D-GUI-1) and never subscribes to a live A2A transport, so the
view renders identically for an in-process run and a real A2A run.

A run with no ``message_flow`` rows (a pre-phase-4 run, or one whose transport recorded none)
yields ``has_flow=False``, and the panel degrades to the Level-1 component-state nodes with no
edges.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# The agent nodes rendered in the message-flow graph, in choreography order (reused from the
# Level-1 view so the two panels place the same agents).
from atlas_conductor.gui.choreography import AGENTS

__all__ = ["AGENTS", "Edge", "MessageFlowState", "message_flow_state"]


@dataclass(frozen=True)
class Edge:
    """One directed inter-agent edge, aggregated over a run's ``message_flow`` rows."""

    from_agent: str
    to_agent: str
    count: int  # how many messages travelled this edge
    last_timestamp: str  # the most recent message on this edge (drives the pulse)


@dataclass(frozen=True)
class MessageFlowState:
    """The derived Level-2 state for one run's message-flow view."""

    edges: list[Edge]  # observed edges, most-recently-active first
    latest: tuple[str, str] | None  # the single most recent (from, to), or None
    has_flow: bool  # False → degrade to the Level-1 component-state view


def message_flow_state(rows: list[dict[str, Any]]) -> MessageFlowState:
    """Derive the message-flow state from a run's ``message_flow`` rows.

    Rows are aggregated per directed ``(from_agent, to_agent)`` pair into an :class:`Edge`
    carrying the message count and the most recent timestamp on that pair. Edges are returned
    most-recently-active first, and ``latest`` names the single most recent edge so the view
    can emphasize it.
    """
    if not rows:
        return MessageFlowState([], None, False)

    aggregated: dict[tuple[str, str], Edge] = {}
    for row in rows:
        from_agent = row.get("from_agent") or ""
        to_agent = row.get("to_agent") or ""
        if not from_agent or not to_agent:
            continue
        timestamp = row.get("timestamp") or ""
        key = (from_agent, to_agent)
        existing = aggregated.get(key)
        if existing is None:
            aggregated[key] = Edge(from_agent, to_agent, 1, timestamp)
        else:
            aggregated[key] = Edge(
                from_agent,
                to_agent,
                existing.count + 1,
                max(existing.last_timestamp, timestamp),
            )

    if not aggregated:
        return MessageFlowState([], None, False)

    edges = sorted(aggregated.values(), key=lambda e: e.last_timestamp, reverse=True)
    latest_edge = edges[0]
    return MessageFlowState(edges, (latest_edge.from_agent, latest_edge.to_agent), True)
