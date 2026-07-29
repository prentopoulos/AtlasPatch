"""The per-slide chain-of-decisions trace (task 8.3, design D15).

The trace is the visible artifact of the thesis that the contribution is the
orchestrator's *decisions*: for each slide it reconstructs the ordered steps that
produced the outcome — reconcile → dispatch → validate(reason) → recover — sourced
entirely from the append-only ``agent_events`` telemetry records. It is rendered in the
terminal report (detail-on-demand) and is the primary content of ``--dry-run``.

Every rendered field is operational metadata (agent id, event, stage, reason code,
tuning/decision summary) — the same PHI-free, no-pixel constraint as the telemetry it
reads (design D9/D11/D12). It adds no computation: the events are already recorded.
"""

from __future__ import annotations

from typing import Any

from atlas_conductor.telemetry import TelemetrySink

# Agent events that constitute a slide's decision chain, in the order they occur.
_TRACE_EVENTS = ("reconcile", "dispatch", "verdict", "blocked", "recover")


def group_traces(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group trace-relevant ``agent_events`` rows by slide stem, preserving order.

    Works on already-read rows so the terminal report (via a sink), the GUI, and the
    report export (both via the read-only reader) share one definition of a slide's
    decision chain and cannot diverge.
    """
    traces: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        stem = event.get("slide_stem")
        if not stem or event.get("event") not in _TRACE_EVENTS:
            continue
        traces.setdefault(stem, []).append(event)
    return traces


def slide_traces(telemetry: TelemetrySink) -> dict[str, list[dict[str, Any]]]:
    """Group the trace-relevant agent events by slide stem, preserving order.

    A write-oriented backend (e.g. the opt-in BigQuery sink, design D-DIST-4) may not
    implement reads — reads are served by the local JSONL backend and the GUI. In that case
    the decision trace degrades to empty rather than crashing the report.
    """
    try:
        events = telemetry.read_agent_events()
    except NotImplementedError:
        return {}
    return group_traces(events)


def render_slide_trace(events: list[dict[str, Any]], indent: str = "      ") -> list[str]:
    """Render one slide's ordered decision steps as text lines."""
    lines: list[str] = []
    for event in events:
        step = f"{indent}{event['agent']}:{event['event']}"
        reason = event.get("reason_code")
        if reason:
            step += f"({reason})"
        detail = event.get("detail")
        if detail:
            step += f" - {detail}"
        lines.append(step)
    return lines
