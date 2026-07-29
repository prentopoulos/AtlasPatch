"""The HTML/JSON machine-readable sibling of the terminal report (report-export spec).

Resolves the D18 open item: the same audit/telemetry data the terminal report prints, in
another shape. It is assembled from the same :func:`build_run_views` structure the GUI
renders, so the exported sibling and the GUI panels cannot diverge, and it reads only the
PHI-free telemetry — pseudonymized stems, structural verdicts, reason codes, counts. It
renders no slide pixel, mask, or confidence score (the HTML contains no ``<img>``).
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from atlas_conductor.gui.model import RunView, build_run_views
from atlas_conductor.gui.reader import TelemetryReader
from atlas_conductor.trace import render_slide_trace


def run_view_to_dict(view: RunView) -> dict[str, Any]:
    """Serialize one run to a JSON-safe dict (the machine-readable report body)."""
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
    }


def export_json(views: list[RunView]) -> str:
    """Render the runs as a JSON document."""
    return json.dumps({"runs": [run_view_to_dict(v) for v in views]}, indent=2, sort_keys=True)


def _counts_line(view: RunView) -> str:
    return "  ".join(f"{outcome}={n}" for outcome, n in view.counts.items())


def export_html(views: list[RunView]) -> str:
    """Render the runs as a self-contained HTML document (no images, no scripts)."""
    parts: list[str] = [
        "<!doctype html>",
        '<meta charset="utf-8">',
        "<title>atlas_conductor run report</title>",
        "<h1>atlas_conductor run report</h1>",
    ]
    if not views:
        parts.append("<p>No runs recorded.</p>")
    for view in views:
        parts.append(f"<h2>run {html.escape(view.job_id)}</h2>")
        parts.append(f"<p>cohort={view.cohort_size} &middot; {html.escape(_counts_line(view))}</p>")
        parts.append("<table><thead><tr>")
        parts.append("<th>slide</th><th>verdict</th><th>reason</th><th>detail</th>")
        parts.append("</tr></thead><tbody>")
        for slide in view.slides:
            trace_text = " ".join(render_slide_trace(slide.trace, indent="")) if slide.trace else ""
            row = (
                f"<tr><td>{html.escape(slide.slide_stem)}</td>"
                f"<td>{html.escape(slide.outcome)}</td>"
                f"<td>{html.escape(slide.reason_code)}</td>"
                f"<td>{html.escape(slide.detail)}</td></tr>"
            )
            parts.append(row)
            if trace_text:
                parts.append(f'<tr><td colspan="4">{html.escape(trace_text)}</td></tr>')
        parts.append("</tbody></table>")
    return "\n".join(parts)


def export_report(telemetry_dir: str | Path, fmt: str = "json") -> str:
    """Read a telemetry directory and render the report sibling in ``fmt`` (json|html)."""
    views = build_run_views(TelemetryReader(telemetry_dir))
    if fmt == "html":
        return export_html(views)
    if fmt == "json":
        return export_json(views)
    raise ValueError(f"unknown report format {fmt!r} (expected 'json' or 'html')")
