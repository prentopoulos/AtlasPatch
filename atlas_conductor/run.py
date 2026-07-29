"""The run orchestration façade — composes plan → dispatch → validate → report.

This is the single in-process coordinator of the four logical components (design D8):
the planner builds a reconciled plan, the scheduler dispatches the first pass and
accounts per slide via the validator, and the report renders the outcome. Wiring the
components as A2A peers is phase 4; here they are plain typed calls.

The façade is also where the phase-2 governance gates are *installed* (design D19/D21):
the configured telemetry sink is wrapped once in a :class:`PhiSafeSink` so every component
writes through the PHI-free gate transparently, and the human-in-the-loop confirmer is
selected from ``JobConfig.unattended``. Both are additive — the underlying phase-1 sink and
scheduler behave identically when unwrapped.

``plan_job`` exposes the planner on its own so ``--dry-run`` (task 4.5) can render the
reconciled plan without any dispatch.
"""

from __future__ import annotations

from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import Plan
from atlas_conductor.dispatch import ExecutionAdapter, FakeAdapter, RealAdapter
from atlas_conductor.governance import AuditTrail, Confirmer, PhiSafeSink, default_confirmer
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


def plan_job(config: JobConfig, telemetry: TelemetrySink, audit: AuditTrail | None = None) -> Plan:
    """Build and reconcile the plan for ``config`` without dispatching anything."""
    return Planner(PhiSafeSink(telemetry, audit=audit)).build_plan(config)


def run_job(
    config: JobConfig,
    telemetry: TelemetrySink,
    adapter: ExecutionAdapter | None = None,
    adapter_name: str = "fake",
    audit: AuditTrail | None = None,
    confirmer: Confirmer | None = None,
) -> RunResult:
    """Plan and execute one job, returning the per-slide run result.

    ``adapter`` defaults to the :class:`FakeAdapter` so the full loop runs with no GPU
    and no real slides (execution-dispatch spec). Pass the real adapter to drive the
    AtlasPatch CLI as a subprocess.

    The configured ``telemetry`` sink is wrapped in a :class:`PhiSafeSink` (design D12), and
    the HITL confirmer defaults to the policy for ``config.unattended`` — hold irreversible
    actions when attended, waive (and record the waiver) when unattended (design D13).
    ``audit`` is the tamper-evident trail consequential actions are appended to.
    """
    if adapter is None:
        adapter = FakeAdapter()
    gated = PhiSafeSink(telemetry, audit=audit)
    if confirmer is None:
        confirmer = default_confirmer(config.unattended)
    plan = Planner(gated).build_plan(config)
    scheduler = Scheduler(
        config,
        adapter,
        gated,
        adapter_name=adapter_name,
        audit=audit,
        confirmer=confirmer,
    )
    return scheduler.run(plan)
