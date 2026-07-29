"""The assembled run view shared by the GUI and the report export (design D-GUI-5).

Both the read-only GUI panels and the HTML/JSON report sibling render from the same
structure built here, so the two surfaces cannot disagree about a run's verdicts or cohort
counts. The assembly reads only the PHI-free telemetry (via :class:`TelemetryReader`) and
carries only operational metadata — slide identifiers exactly as persisted (pseudonymized
for gated runs), structural verdicts with reason codes, and the decision trace. No pixels,
no confidence scores, no ``atlas_patch`` import.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from atlas_conductor.gui.reader import TelemetryReader
from atlas_conductor.trace import group_traces

# The terminal outcomes a slide can end a run at, in report order.
TERMINAL_OUTCOMES = ("valid", "skipped", "quarantined", "blocked")


@dataclass(frozen=True)
class SlideView:
    """One slide's terminal accounting, assembled from telemetry."""

    slide_stem: str  # exactly as persisted (a pseudonym for gated runs)
    outcome: str  # a TERMINAL_OUTCOMES value — a structural verdict, never a score
    reason_code: str
    detail: str
    trace: list[dict[str, Any]]  # ordered decision events (agent_events)


@dataclass(frozen=True)
class RunView:
    """A whole run assembled for rendering: its job row and per-slide verdicts."""

    job_id: str
    job: dict[str, Any]
    slides: list[SlideView]

    @property
    def cohort_size(self) -> int:
        return len(self.slides)

    def count(self, outcome: str) -> int:
        return sum(1 for slide in self.slides if slide.outcome == outcome)

    @property
    def counts(self) -> dict[str, int]:
        return {outcome: self.count(outcome) for outcome in TERMINAL_OUTCOMES}


def _group_by_job(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row.get("job_id", ""), []).append(row)
    return grouped


def _build_run_view(
    job: dict[str, Any],
    outcomes: list[dict[str, Any]],
    validations: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> RunView:
    # Terminal outcome per slide = the last-appended stage outcome (append order is
    # chronological), matching the report's per-slide accounting.
    terminal: dict[str, dict[str, Any]] = {}
    for row in outcomes:
        terminal[row.get("slide_stem", "")] = row
    # Detail comes from the slide's last validation row (the verdict's human-readable note).
    detail_for: dict[str, str] = {}
    for row in validations:
        detail_for[row.get("slide_stem", "")] = row.get("detail", "")

    traces = group_traces(events)
    slides = [
        SlideView(
            slide_stem=stem,
            outcome=row.get("outcome", ""),
            reason_code=row.get("reason_code", ""),
            detail=detail_for.get(stem, ""),
            trace=traces.get(stem, []),
        )
        for stem, row in sorted(terminal.items())
    ]
    return RunView(job_id=job.get("job_id", ""), job=job, slides=slides)


def build_run_views(reader: TelemetryReader) -> list[RunView]:
    """Assemble one :class:`RunView` per recorded job, newest last (append order)."""
    outcomes_by_job = _group_by_job(reader.slide_stage_outcomes())
    validations_by_job = _group_by_job(reader.validation_results())
    events_by_job = _group_by_job(reader.agent_events())
    views: list[RunView] = []
    for job in reader.jobs():
        job_id = job.get("job_id", "")
        views.append(
            _build_run_view(
                job,
                outcomes_by_job.get(job_id, []),
                validations_by_job.get(job_id, []),
                events_by_job.get(job_id, []),
            )
        )
    return views
