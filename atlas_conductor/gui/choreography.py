"""The Level-1 agent-choreography state (agent-choreography spec, design D18, D-GUI-4).

The component-state view shows the four logical agents (planner, worker, validator,
recovery) plus the scheduler loop as active (lit) or idle (dim), with a "now processing
slide X · stage Y" ticker. Everything here is *derived* from the existing ``agent_events``
rows — the most-recent actor and the latest slide/stage — so it needs no A2A wiring and no
new telemetry family. Level-2 true message-flow (edges between agents) is out of scope; this
module computes no inter-agent edges.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# The logical agents rendered in the component-state view, in choreography order.
AGENTS = ("planner", "worker", "validator", "recovery", "scheduler")


@dataclass(frozen=True)
class ChoreographyState:
    """The derived lit/dim state and ticker for one run's choreography view."""

    active: str | None  # the most-recent actor, or None when no events yet
    lit: dict[str, bool]  # agent -> active(True) / idle(False)
    slide_stem: str | None  # slide named by the latest event (as persisted)
    stage: str | None  # stage named by the latest event
    now_processing: str | None  # "slide X · stage Y", or None when idle


def choreography_state(events: list[dict[str, Any]]) -> ChoreographyState:
    """Derive the choreography state from a run's ordered ``agent_events`` rows.

    The active agent is the actor of the latest event; every other agent is idle. The
    ticker follows the latest event's slide/stage and idles when the latest event names no
    slide (e.g. planning or run completion).
    """
    if not events:
        return ChoreographyState(None, {agent: False for agent in AGENTS}, None, None, None)

    last = events[-1]
    active = last.get("agent")
    lit = {agent: (agent == active) for agent in AGENTS}
    stem = last.get("slide_stem") or None
    stage = last.get("stage") or None
    if stem and stage:
        now_processing: str | None = f"slide {stem} · stage {stage}"
    elif stem:
        now_processing = f"slide {stem}"
    else:
        now_processing = None
    return ChoreographyState(active, lit, stem, stage, now_processing)
