"""Unit tests for the Level-2 message-flow derivation (task 5.1, agent-choreography spec).

Edges are aggregated per directed ``(from_agent, to_agent)`` pair with a message count and
the most recent timestamp; the most recently active edge is ``latest``; an empty family
yields ``has_flow=False`` so the panel degrades to Level-1. This logic is streamlit-free, so
it is covered here (and on the core test env) independently of the AppTest.
"""

from __future__ import annotations

from atlas_conductor.gui.messageflow import message_flow_state


def _row(from_agent: str, to_agent: str, timestamp: str) -> dict:
    return {"from_agent": from_agent, "to_agent": to_agent, "timestamp": timestamp}


def test_no_rows_degrade_to_level_1() -> None:
    state = message_flow_state([])
    assert state.has_flow is False
    assert state.edges == []
    assert state.latest is None


def test_rows_with_no_agents_degrade() -> None:
    # Rows missing from/to agents contribute no edge (defensive) and degrade the view.
    state = message_flow_state([{"timestamp": "t1"}, {"from_agent": "planner"}])
    assert state.has_flow is False


def test_edges_aggregate_count_and_recency() -> None:
    rows = [
        _row("planner", "worker", "t1"),
        _row("worker", "validator", "t2"),
        _row("planner", "worker", "t3"),  # second message on the same edge
        _row("validator", "recovery", "t4"),
    ]
    state = message_flow_state(rows)

    assert state.has_flow is True
    edges = {(e.from_agent, e.to_agent): e for e in state.edges}
    assert edges[("planner", "worker")].count == 2
    assert edges[("planner", "worker")].last_timestamp == "t3"
    assert edges[("worker", "validator")].count == 1
    # The single most recent edge is emphasized, and edges are ordered most-recent first.
    assert state.latest == ("validator", "recovery")
    assert (state.edges[0].from_agent, state.edges[0].to_agent) == ("validator", "recovery")
