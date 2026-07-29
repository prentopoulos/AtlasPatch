"""The run orchestration façade — composes plan → dispatch → validate → report.

This is the single in-process coordinator of the four logical components for slice A1
(design D8): the planner builds a reconciled plan, the scheduler dispatches the first
pass and accounts per slide via the validator, and the report renders the outcome.
Wiring the components as A2A peers is phase 4; here they are plain typed calls.
"""

from __future__ import annotations

from atlas_conductor.config import JobConfig
from atlas_conductor.dispatch import ExecutionAdapter, FakeAdapter
from atlas_conductor.planning import Planner, discover_cohort
from atlas_conductor.scheduler import RunResult, Scheduler
from atlas_conductor.telemetry import TelemetrySink


def run_job(
    config: JobConfig,
    telemetry: TelemetrySink,
    adapter: ExecutionAdapter | None = None,
    adapter_name: str = "fake",
) -> RunResult:
    """Plan and execute one job, returning the per-slide run result.

    ``adapter`` defaults to the :class:`FakeAdapter` so the full loop runs with no GPU
    and no real slides (execution-dispatch spec). Pass the real adapter (slice A2) to
    drive the AtlasPatch CLI as a subprocess.
    """
    if adapter is None:
        adapter = FakeAdapter()
    slide_paths = discover_cohort(config.input_dir)
    planner = Planner(telemetry)
    plan = planner.build_plan(config, slide_paths)
    scheduler = Scheduler(config, adapter, telemetry, adapter_name=adapter_name)
    return scheduler.run(plan)
