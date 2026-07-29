"""The single execution-adapter interface (task 5.1).

Every adapter — the real subprocess adapter (phase-1 slice A2) and the fake adapter
(slice A1) — satisfies this one interface, and selecting an adapter changes no other
component's code path (execution-dispatch spec). The adapter receives a declarative
:class:`~atlas_conductor.contracts.Task` and translates it into its own action,
returning a raw, unclassified :class:`~atlas_conductor.contracts.Outcome`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from atlas_conductor.contracts import Outcome, Task


class ExecutionAdapter(ABC):
    """Translate a declarative task into an execution and return its raw outcome."""

    @abstractmethod
    def execute(self, task: Task) -> Outcome:
        """Run the task's work; return exit code, output tails, timing, produced paths."""
        raise NotImplementedError
