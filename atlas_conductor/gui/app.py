"""The read-only observability GUI (observability-gui spec, design D18).

A Streamlit renderer over the PHI-free telemetry: run history, per-slide verdicts, the
decision trace, cohort metrics, and the Level-1 agent-choreography view. This is the only
module in the package that imports ``streamlit`` — the reader, model, and choreography
helpers stay dependency-free so the core CLI import graph never pulls in the GUI runtime
(enforced by a CI import-guard test).

The GUI is **read-only**: it presents no control that submits a job, confirms a HITL action,
or writes telemetry. It renders no slide pixel and no confidence score — verdicts are the
validator's structural pass/fail with a reason code, and slide identifiers are shown exactly
as persisted (pseudonymized for gated runs).
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from atlas_conductor.gui.choreography import AGENTS, choreography_state
from atlas_conductor.gui.model import TERMINAL_OUTCOMES, RunView, build_run_views
from atlas_conductor.gui.reader import TelemetryReader
from atlas_conductor.trace import render_slide_trace

TELEMETRY_DIR_ENV = "ATLAS_CONDUCTOR_TELEMETRY_DIR"


def _telemetry_dir() -> Path:
    """Resolve the telemetry directory to observe.

    Precedence: an explicit ``telemetry_dir`` in session state (used by the AppTest
    harness), then the ``ATLAS_CONDUCTOR_TELEMETRY_DIR`` env var, then a sidebar text input
    defaulting to ``telemetry``.
    """
    if "telemetry_dir" in st.session_state:
        return Path(st.session_state["telemetry_dir"])
    default = os.environ.get(TELEMETRY_DIR_ENV, "telemetry")
    return Path(st.sidebar.text_input("Telemetry directory", value=default))


def _render_history(views: list[RunView]) -> None:
    st.header("Run history")
    st.dataframe(
        [
            {
                "job_id": view.job_id,
                "status": view.job.get("status", ""),
                "cohort": view.cohort_size,
                **view.counts,
            }
            for view in views
        ]
    )


def _select_run(views: list[RunView]) -> RunView:
    job_ids = [view.job_id for view in views]
    # Default to the most recent run (append order → last).
    selected = st.selectbox("Run", job_ids, index=len(job_ids) - 1)
    return next(view for view in views if view.job_id == selected)


def _render_choreography(view: RunView) -> None:
    st.subheader("Agent choreography")
    state = choreography_state(view.events)
    for agent in AGENTS:
        marker = "🟢 active" if state.lit.get(agent) else "⚪ idle"
        st.markdown(f"**{agent}** — {marker}")
    if state.now_processing:
        st.markdown(f"Now processing: {state.now_processing}")
    else:
        st.markdown("Now processing: idle")


def _render_metrics(view: RunView) -> None:
    st.subheader("Cohort metrics")
    st.metric("cohort", view.cohort_size)
    for outcome in TERMINAL_OUTCOMES:
        st.metric(outcome, view.count(outcome))


def _render_verdicts(view: RunView) -> None:
    st.subheader("Per-slide verdicts")
    st.dataframe(
        [
            {
                "slide": slide.slide_stem,
                "verdict": slide.outcome,
                "reason": slide.reason_code,
                "detail": slide.detail,
            }
            for slide in view.slides
        ]
    )


def _render_trace(view: RunView) -> None:
    st.subheader("Decision trace")
    for slide in view.slides:
        if not slide.trace:
            continue
        with st.expander(f"{slide.slide_stem} — {slide.outcome}"):
            for line in render_slide_trace(slide.trace, indent=""):
                st.markdown(line)


def main() -> None:
    st.title("AtlasPatch Conductor — observability")
    st.caption(
        "Read-only view over the PHI-free telemetry — verdicts, not predictions; "
        "decision trace, not saliency; no slide pixels."
    )
    reader = TelemetryReader(_telemetry_dir())
    if reader.is_empty():
        st.info("No runs recorded yet.")
        return

    views = build_run_views(reader)
    _render_history(views)
    view = _select_run(views)
    _render_choreography(view)
    _render_metrics(view)
    _render_verdicts(view)
    _render_trace(view)


main()
