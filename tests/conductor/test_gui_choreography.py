"""Unit tests for the Level-1 choreography derivation (task 6.3, agent-choreography spec).

The active agent is the latest actor, all others idle; the ticker follows the latest
event's slide/stage and idles when the latest event names no slide; the state carries no
inter-agent message edges (Level-2 is out of scope).
"""

from __future__ import annotations

import dataclasses

from atlas_conductor.gui.choreography import AGENTS, ChoreographyState, choreography_state


def _event(agent: str, slide_stem: str | None = None, stage: str | None = None) -> dict:
    return {"agent": agent, "event": "x", "slide_stem": slide_stem, "stage": stage}


def test_empty_events_leave_every_agent_idle() -> None:
    state = choreography_state([])
    assert state.active is None
    assert all(lit is False for lit in state.lit.values())
    assert state.now_processing is None


def test_latest_actor_is_active_and_others_idle() -> None:
    events = [
        _event("planner"),
        _event("worker", "s1", "segment"),
        _event("validator", "s1", "segment"),
    ]
    state = choreography_state(events)
    assert state.active == "validator"
    assert state.lit["validator"] is True
    assert state.lit["planner"] is False and state.lit["worker"] is False


def test_ticker_follows_latest_slide_and_stage() -> None:
    state = choreography_state([_event("worker", "slideB", "embed")])
    assert state.slide_stem == "slideB" and state.stage == "embed"
    assert state.now_processing is not None
    assert "slideB" in state.now_processing and "embed" in state.now_processing


def test_ticker_idles_when_latest_event_names_no_slide() -> None:
    # A planning / completion event carries no slide → the ticker idles rather than showing
    # a stale slide.
    state = choreography_state([_event("worker", "slideB", "embed"), _event("planner")])
    assert state.now_processing is None


def test_state_has_no_message_flow_edges() -> None:
    # Level-2 message-flow (edges between agents) is out of scope: the state models
    # component-state only.
    field_names = {f.name for f in dataclasses.fields(ChoreographyState)}
    assert "edges" not in field_names and "messages" not in field_names
    assert len(AGENTS) == 5  # planner, worker, validator, recovery, scheduler
