"""The four logical agents' identities (task 1.1).

Per design D8 the planner, worker, validator, and recovery agents are built here as
plain in-process typed components; the scheduler is a deterministic resource governor,
not a fifth agent. Wiring these components as A2A peers on Google ADK is phase 4
(``add-conductor-distribution``) — the core produces identical outputs without a
message bus, so this module carries only the agent identities that label
``agent_events`` records. Those events drive the decision trace (design D15) and the
GUI Level 1 component-state view (design D18).
"""

from __future__ import annotations

from enum import Enum


class Agent(str, Enum):
    PLANNER = "planner"
    WORKER = "worker"
    VALIDATOR = "validator"
    RECOVERY = "recovery"
    SCHEDULER = "scheduler"
