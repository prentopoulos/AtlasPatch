"""The HTML/JSON machine-readable sibling of the terminal report (report-export spec).

Resolves the D18 open item: the same audit/telemetry data the terminal report prints, in
another shape. Both siblings are assembled from the same :func:`build_run_views` structure the
GUI renders, so the exported sibling and the GUI panels cannot diverge, and they read only the
PHI-free telemetry — pseudonymized stems, structural verdicts, reason codes, counts. Neither
renders a slide pixel, mask, or confidence score (the HTML contains no ``<img>``).

The JSON sibling **is** the versioned :mod:`~atlas_conductor.gui.snapshot` payload — the single
machine-readable observability shape (design D-SNAP-3) — so it additionally carries each run's
derived choreography and message-flow state and a schema version a renderer can pin. The HTML
sibling keeps its own assembly from :func:`build_run_views`; a test asserts the two agree.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from atlas_conductor.gui.model import RunView, build_run_views
from atlas_conductor.gui.reader import TelemetryReader
from atlas_conductor.gui.snapshot import assemble_snapshot
from atlas_conductor.trace import render_slide_trace


def export_json(source: TelemetryReader | str | Path) -> str:
    """Render the telemetry as the versioned JSON snapshot document (D-SNAP-3)."""
    return json.dumps(assemble_snapshot(source), indent=2, sort_keys=True)


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
    reader = TelemetryReader(telemetry_dir)
    if fmt == "html":
        return export_html(build_run_views(reader))
    if fmt == "json":
        return export_json(reader)
    raise ValueError(f"unknown report format {fmt!r} (expected 'json' or 'html')")
