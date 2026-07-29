"""The execution worker (task 5.4).

The worker is deliberately thin: it hands a task to the configured adapter and
forwards the *raw, unclassified* outcome (execution-dispatch spec). It does not
classify failures or decide recovery actions — that is the recovery agent's job
(slice A3). Its only added behavior is emitting an ``agent_events`` record so the
dispatch step is visible in the decision trace and the GUI component-state view.
"""

from __future__ import annotations

from atlas_conductor.agents import Agent
from atlas_conductor.contracts import Outcome, Task
from atlas_conductor.dispatch.base import ExecutionAdapter
from atlas_conductor.telemetry import AgentEventRecord, TelemetrySink


class Worker:
    """Dispatch a task to an adapter and forward its raw outcome unchanged."""

    def __init__(self, adapter: ExecutionAdapter, telemetry: TelemetrySink, job_id: str) -> None:
        self._adapter = adapter
        self._telemetry = telemetry
        self._job_id = job_id

    def execute(self, task: Task) -> Outcome:
        stems = ", ".join(t.slide_stem for t in task.targets)
        self._telemetry.record_agent_event(
            AgentEventRecord(
                job_id=self._job_id,
                agent=Agent.WORKER.value,
                event="dispatch",
                stage=task.stage.value,
                detail=f"command={task.command.value} targets=[{stems}] attempt={task.attempt}",
            )
        )
        return self._adapter.execute(task)
