"""The run orchestration façade — composes plan → dispatch → validate → report.

This is the single in-process coordinator of the four logical components (design D8):
the planner builds a reconciled plan, the scheduler dispatches the first pass and
accounts per slide via the validator, and the report renders the outcome. Wiring the
components as A2A peers is phase 4; here they are plain typed calls.

``plan_job`` exposes the planner on its own so ``--dry-run`` (task 4.5) can render the
reconciled plan without any dispatch.
"""

from __future__ import annotations

from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import Plan
from atlas_conductor.dispatch import ExecutionAdapter, FakeAdapter, RealAdapter
from atlas_conductor.planning import Planner
from atlas_conductor.scheduler import RunResult, Scheduler
from atlas_conductor.telemetry import TelemetrySink


def make_adapter(name: str) -> tuple[ExecutionAdapter, str]:
    """Resolve an adapter by name. ``fake`` needs no GPU; ``real`` drives the CLI."""
    if name == "fake":
        return FakeAdapter(), "fake"
    if name == "real":
        return RealAdapter(), "real"
    raise ValueError(f"unknown adapter {name!r}; choose 'fake' or 'real'")


def plan_job(config: JobConfig, telemetry: TelemetrySink) -> Plan:
    """Build and reconcile the plan for ``config`` without dispatching anything."""
    return Planner(telemetry).build_plan(config)


def run_job(
    config: JobConfig,
    telemetry: TelemetrySink,
    adapter: ExecutionAdapter | None = None,
    adapter_name: str = "fake",
) -> RunResult:
    """Plan and execute one job, returning the per-slide run result.

    ``adapter`` defaults to the :class:`FakeAdapter` so the full loop runs with no GPU
    and no real slides (execution-dispatch spec). Pass the real adapter to drive the
    AtlasPatch CLI as a subprocess.
    """
    if adapter is None:
        adapter = FakeAdapter()
    plan = Planner(telemetry).build_plan(config)
    scheduler = Scheduler(config, adapter, telemetry, adapter_name=adapter_name)
    return scheduler.run(plan)
