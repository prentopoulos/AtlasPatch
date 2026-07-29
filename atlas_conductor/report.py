"""The terminal summary report and the dry-run report (tasks 8.2, 8.3, 4.5).

The report states, per slide, the terminal stage outcome and the reason for any
non-valid outcome, plus cohort-level counts (orchestration-run spec). It reflects the
validator's per-slide verdicts, never the AtlasPatch CLI exit code (design D3).

It is summary-first (design D15): the outcome table and counts always print, and the
per-slide chain-of-decisions trace is detail-on-demand — shown for non-valid slides by
default, for all slides on request, and as the primary content of ``--dry-run``. The
trace is sourced from the append-only telemetry records (design D15, task 8.3).
"""

from __future__ import annotations

from atlas_conductor.contracts import STAGES_FOR_OUTPUT, Decision, Plan, SlideOutcome
from atlas_conductor.scheduler import RunResult
from atlas_conductor.telemetry import TelemetrySink
from atlas_conductor.trace import render_slide_trace, slide_traces

_ORDER = (
    SlideOutcome.VALID,
    SlideOutcome.SKIPPED,
    SlideOutcome.QUARANTINED,
    SlideOutcome.BLOCKED,
)


def build_report(
    result: RunResult,
    telemetry: TelemetrySink | None = None,
    trace: str = "failures",
) -> str:
    """Render the terminal summary report.

    ``trace`` controls the detail-on-demand decision trace: ``"failures"`` (default)
    shows it for non-valid slides, ``"all"`` for every slide, ``"none"`` suppresses it.
    A trace requires ``telemetry`` (the record source).
    """
    plan = result.plan
    lines: list[str] = [
        "=" * 60,
        f"atlas_conductor run {result.job_id}",
        f"cohort={plan.input_dir}  output={plan.requested_output.value}  "
        f"geometry=ps{plan.geometry.patch_size}/mag{plan.geometry.target_mag}",
        "-" * 60,
    ]

    traces = slide_traces(telemetry) if telemetry is not None and trace != "none" else {}
    for slide in sorted(result.slides, key=lambda s: s.slide_stem):
        line = f"  {slide.slide_stem:<32} {slide.outcome.value:<12}"
        if slide.outcome is not SlideOutcome.VALID and slide.reason.value != "valid":
            line += f" {slide.reason.value}"
            if slide.detail:
                line += f" - {slide.detail}"
        lines.append(line)
        show = trace == "all" or (trace == "failures" and slide.outcome is not SlideOutcome.VALID)
        if show and slide.slide_stem in traces:
            lines.extend(render_slide_trace(traces[slide.slide_stem]))

    lines.append("-" * 60)
    counts = "  ".join(f"{outcome.value}={result.count(outcome)}" for outcome in _ORDER)
    lines.append(f"  cohort={result.cohort_size}  {counts}")
    lines.append("=" * 60)
    return "\n".join(lines)


def build_dry_run_report(plan: Plan, telemetry: TelemetrySink | None = None) -> str:
    """Render the reconciled plan without any dispatch (task 4.5).

    Shows each slide's terminal reconciliation decision (skip/run/reuse/blocked) with
    its reason, plus the per-slide decision trace. Dispatches no work.
    """
    lines: list[str] = [
        "=" * 60,
        f"atlas_conductor DRY RUN {plan.job_id}",
        f"cohort={plan.input_dir}  output={plan.requested_output.value}  "
        f"geometry=ps{plan.geometry.patch_size}/mag{plan.geometry.target_mag}",
        "-" * 60,
    ]

    if plan.is_blocked:
        assert plan.blocked_reason is not None  # is_blocked ⇔ blocked_reason set
        lines.append(f"  COHORT BLOCKED  {plan.blocked_reason.value}  - {plan.blocked_detail}")
        lines.append("=" * 60)
        return "\n".join(lines)

    terminal_stage = STAGES_FOR_OUTPUT[plan.requested_output][-1]
    terminal_nodes = plan.nodes_for(terminal_stage)
    traces = slide_traces(telemetry) if telemetry is not None else {}
    counts: dict[str, int] = {d.value: 0 for d in Decision}

    for node in sorted(terminal_nodes, key=lambda n: n.slide_stem):
        counts[node.decision.value] += 1
        line = f"  {node.slide_stem:<32} {node.decision.value:<10}"
        if node.reason and node.reason.value != "valid":
            line += f" {node.reason.value}"
            if node.detail:
                line += f" - {node.detail}"
        lines.append(line)
        if node.slide_stem in traces:
            lines.extend(render_slide_trace(traces[node.slide_stem]))

    lines.append("-" * 60)
    summary = "  ".join(f"{k}={v}" for k, v in counts.items() if v)
    lines.append(f"  cohort={len(terminal_nodes)}  {summary}  (no work dispatched)")
    lines.append("=" * 60)
    return "\n".join(lines)
