"""The frozen, schema-versioned observability snapshot (gui-snapshot spec, design D-SNAP-*).

Phase 3 shipped two renderers over the same telemetry read path — the Streamlit ``app.py`` and
the ``export.py`` JSON/HTML sibling — but no single, complete, versioned payload a *third*
renderer could pin. This module freezes that seam: :func:`assemble_snapshot` serializes a
telemetry directory into one JSON-safe payload carrying everything the observability surface
shows — per run: the job/history row, the per-slide structural verdicts, the decision trace,
the cohort metrics, and the **derived** Level-1 choreography and Level-2 message-flow state that
today are computed only at Streamlit render time. Phase 9's React renderer pins
:data:`SNAPSHOT_SCHEMA_VERSION` and consumes this shape.

The payload carries the D18/observability invariants as a *contract*, asserted by first-class
tests (design D-SNAP-4): it is PHI-free (slide stems exactly as persisted — pseudonyms for gated
runs, never a raw identifier), holds no slide pixel / mask / heatmap / embedding, and holds no
confidence, probability, or diagnostic score — verdicts are structural pass/fail plus a reason
code only. Assembly reuses the *same* :func:`choreography_state` / :func:`message_flow_state`
derivations the GUI renders, so the payload cannot diverge from what the GUI derives at render
time (D-SNAP-1).

The module imports only the dependency-free GUI helpers (``reader``, ``model``,
``choreography``, ``messageflow``) and never ``streamlit`` or ``atlas_patch`` (D-SNAP-5), so the
contract is consumable by any renderer's build tooling without the GUI runtime.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from atlas_conductor.gui.choreography import AGENTS, choreography_state
from atlas_conductor.gui.messageflow import message_flow_state
from atlas_conductor.gui.model import RunView, build_run_views
from atlas_conductor.gui.reader import TelemetryReader

# The payload's schema version. A renderer (phase 9) pins this value; bump it only on a
# breaking shape change (D-SNAP-2). A top-level integer is the smallest thing that gives a
# single-producer/single-consumer contract a stable compatibility handle.
SNAPSHOT_SCHEMA_VERSION = 1


def run_snapshot(view: RunView) -> dict[str, Any]:
    """Serialize one run into a JSON-safe dict: verdicts, trace, counts, and derived state.

    Reuses the :class:`RunView` / :class:`SlideView` shape (job row, per-slide structural
    verdicts with reason code + detail + trace, cohort metrics) and adds the run's derived
    Level-1 choreography and Level-2 message-flow state — the *same* derivations the GUI
    renders (D-SNAP-1, D-SNAP-3), serialized here once.
    """
    flow = asdict(message_flow_state(view.message_flow))
    # Normalize the ``latest`` (from, to) tuple to a JSON-native list so the payload looks
    # identical before and after ``json.dumps`` (the contract is a JSON shape, not a Python one).
    flow["latest"] = list(flow["latest"]) if flow["latest"] is not None else None
    return {
        "job_id": view.job_id,
        "job": view.job,
        "cohort_size": view.cohort_size,
        "counts": view.counts,
        "slides": [
            {
                "slide_stem": slide.slide_stem,
                "outcome": slide.outcome,
                "reason_code": slide.reason_code,
                "detail": slide.detail,
                "trace": slide.trace,
            }
            for slide in view.slides
        ],
        "choreography": asdict(choreography_state(view.events)),
        "message_flow": flow,
    }


def assemble_snapshot(source: TelemetryReader | str | Path) -> dict[str, Any]:
    """Assemble a telemetry directory (or reader) into the versioned snapshot payload.

    Accepts either a :class:`TelemetryReader` or a telemetry directory path. Empty telemetry
    yields the versioned payload with an empty ``runs`` list, raising no exception
    (gui-snapshot: empty telemetry). The top-level ``agents`` roster frees a renderer from
    hardcoding agent order (task 1.5).
    """
    reader = source if isinstance(source, TelemetryReader) else TelemetryReader(source)
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "agents": list(AGENTS),
        "runs": [run_snapshot(view) for view in build_run_views(reader)],
    }
