"""The terminal summary report (task 8.2).

The report states, per slide, the terminal stage outcome and the reason for any
non-valid outcome, plus cohort-level counts (orchestration-run spec). It reflects the
validator's per-slide verdicts, never the AtlasPatch CLI exit code (design D3).

Slice A1 renders the summary-first outcome view. The per-slide chain-of-decisions
trace (design D15, task 8.3) — reconcile → dispatch → validate(reason) → recover,
sourced from the ``agent_events``/``slide_stage_outcomes`` telemetry — is layered on
in slice A2 as detail-on-demand.
"""

from __future__ import annotations

from atlas_conductor.contracts import SlideOutcome
from atlas_conductor.scheduler import RunResult

_ORDER = (
    SlideOutcome.VALID,
    SlideOutcome.SKIPPED,
    SlideOutcome.QUARANTINED,
    SlideOutcome.BLOCKED,
)


def build_report(result: RunResult) -> str:
    """Render the terminal summary report as text."""
    plan = result.plan
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append(f"atlas_conductor run {result.job_id}")
    lines.append(
        f"cohort={plan.input_dir}  output={plan.requested_output.value}  "
        f"geometry=ps{plan.geometry.patch_size}/mag{plan.geometry.target_mag}"
    )
    lines.append("-" * 60)

    for slide in sorted(result.slides, key=lambda s: s.slide_stem):
        line = f"  {slide.slide_stem:<32} {slide.outcome.value:<12}"
        if slide.outcome is not SlideOutcome.VALID and slide.reason.value != "valid":
            line += f" {slide.reason.value}"
            if slide.detail:
                line += f" — {slide.detail}"
        lines.append(line)

    lines.append("-" * 60)
    counts = "  ".join(f"{outcome.value}={result.count(outcome)}" for outcome in _ORDER)
    lines.append(f"  cohort={result.cohort_size}  {counts}")
    lines.append("=" * 60)
    return "\n".join(lines)
