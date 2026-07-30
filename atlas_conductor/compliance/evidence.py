"""The run-scoped compliance evidence bundle (design D-CMP-3/D-CMP-4).

:func:`build_evidence` assembles, for the runs in a telemetry directory, a PHI-free
conformity snapshot: the audit chain **verified** (not trusted), the governance decisions
actually recorded (HITL holds/approvals/waivers, telemetry-gate rejections), the per-slide
operational outcomes and cohort counts, and the static control-register summary. It is a
*reader* — it introduces no new telemetry/audit field and no write path.

Two load-bearing choices:

* **Shared read path (D-CMP-3).** Runs are read through the very same
  :func:`~atlas_conductor.gui.model.build_run_views` over :class:`TelemetryReader` that the
  GUI and ``export-report`` use, so the bundle's per-slide verdicts and cohort counts are
  identical to the report by construction, and it inherits the PHI-free guarantee for free —
  that path never exposes a raw stem or a pixel.

* **Verify, never assert (D-CMP-4).** The audit trail is a *single* hash chain for the whole
  telemetry directory (entries from multiple runs are interleaved in one chain), so a per-run
  *subset* could not be re-verified — filtering by ``job_id`` would break the ``prev_hash``
  links. The bundle therefore verifies the **whole trail once** with :func:`verify_audit_chain`
  and surfaces that single verdict (a tampered entry anywhere reports the trail **broken**),
  then attributes governance decisions to runs by the ``job_id`` each audit payload carries.
  This resolves the design's open question: chain integrity is a directory-level property; the
  decisions are the run-level content.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from atlas_conductor.compliance.registry import RegistryError, load_registry
from atlas_conductor.governance.audit import ChainVerification, verify_audit_chain
from atlas_conductor.gui.model import RunView, build_run_views
from atlas_conductor.gui.reader import TelemetryReader

# The audit trail is a sibling of telemetry; by convention it lives inside the telemetry
# directory as ``audit.jsonl`` (JsonlAuditTrail's persisted form). A directory with no trail
# reads as zero entries — a chain of length zero verifies intact trivially.
AUDIT_FILENAME = "audit.jsonl"

# Audit actions that are consequential governance decisions surfaced in the bundle.
_HITL_ACTIONS = ("hitl-hold", "hitl-approve", "hitl-waiver")
_GATE_ACTION = "phi-gate-rejection"
_DECISION_ACTIONS = (*_HITL_ACTIONS, _GATE_ACTION)


@dataclass(frozen=True)
class SlideEvidence:
    """One slide's operational verdict, taken verbatim from the shared run view."""

    slide_stem: str
    outcome: str
    reason_code: str
    detail: str


@dataclass(frozen=True)
class GovernanceDecision:
    """One recorded HITL or gate decision, attributed to a run by ``job_id``."""

    action: str
    slide_stem: str
    stage: str
    detail: str


@dataclass(frozen=True)
class RunEvidence:
    """The conformity evidence for one run."""

    job_id: str
    cohort_size: int
    counts: dict[str, int]
    slides: list[SlideEvidence]
    governance_decisions: list[GovernanceDecision]

    @property
    def decision_counts(self) -> dict[str, int]:
        """A per-action tally of this run's governance decisions (all actions present)."""
        counts = dict.fromkeys(_DECISION_ACTIONS, 0)
        for decision in self.governance_decisions:
            if decision.action in counts:
                counts[decision.action] += 1
        return counts


@dataclass(frozen=True)
class RegistrySummary:
    """The static control-register's pass/fail summary attached to the bundle."""

    well_formed: bool
    total: int
    by_framework: dict[str, int]
    control_ids: list[str]
    error: str = ""


@dataclass(frozen=True)
class EvidenceBundle:
    """A PHI-free conformity snapshot for the runs in a telemetry directory."""

    telemetry_dir: str
    audit_chain: ChainVerification
    audit_entry_count: int
    runs: list[RunEvidence] = field(default_factory=list)
    controls: RegistrySummary = field(
        default_factory=lambda: RegistrySummary(False, 0, {}, [], "not loaded")
    )


# -- assembly ------------------------------------------------------------------------------


def _slides_for(view: RunView) -> list[SlideEvidence]:
    return [
        SlideEvidence(
            slide_stem=slide.slide_stem,
            outcome=slide.outcome,
            reason_code=slide.reason_code,
            detail=slide.detail,
        )
        for slide in view.slides
    ]


def _decisions_by_job(entries: list[dict[str, Any]]) -> dict[str, list[GovernanceDecision]]:
    """Group the consequential HITL/gate decisions in the trail by their ``job_id``."""
    grouped: dict[str, list[GovernanceDecision]] = {}
    for row in entries:
        action = row.get("action", "")
        if action not in _DECISION_ACTIONS:
            continue
        payload = row.get("payload", {})
        decision = GovernanceDecision(
            action=action,
            slide_stem=str(payload.get("slide_stem", "") or ""),
            stage=str(payload.get("stage", "") or ""),
            detail=str(payload.get("detail", "") or ""),
        )
        grouped.setdefault(str(payload.get("job_id", "")), []).append(decision)
    return grouped


def _summarize_registry(registry_path: str | Path | None) -> RegistrySummary:
    try:
        rows = load_registry(registry_path)
    except RegistryError as exc:
        return RegistrySummary(False, 0, {}, [], str(exc))
    by_framework: dict[str, int] = {}
    for row in rows:
        by_framework[row.framework] = by_framework.get(row.framework, 0) + 1
    return RegistrySummary(True, len(rows), by_framework, [row.id for row in rows])


def build_evidence(
    telemetry_dir: str | Path,
    *,
    audit_path: str | Path | None = None,
    registry_path: str | Path | None = None,
) -> EvidenceBundle:
    """Assemble the evidence bundle for the runs recorded under ``telemetry_dir``.

    ``audit_path`` defaults to ``<telemetry_dir>/audit.jsonl``; ``registry_path`` defaults to
    the shipped control register. The bundle reads only the PHI-free telemetry/audit path, so
    it carries no slide pixel, mask, embedding, or raw identifier.
    """
    telemetry_dir = Path(telemetry_dir)
    views = build_run_views(TelemetryReader(telemetry_dir))

    trail_path = Path(audit_path) if audit_path is not None else telemetry_dir / AUDIT_FILENAME
    entries = _read_audit_entries(trail_path)
    chain = verify_audit_chain(entries)
    decisions_by_job = _decisions_by_job(entries)

    runs = [
        RunEvidence(
            job_id=view.job_id,
            cohort_size=view.cohort_size,
            counts=view.counts,
            slides=_slides_for(view),
            governance_decisions=decisions_by_job.get(view.job_id, []),
        )
        for view in views
    ]

    return EvidenceBundle(
        telemetry_dir=str(telemetry_dir),
        audit_chain=chain,
        audit_entry_count=len(entries),
        runs=runs,
        controls=_summarize_registry(registry_path),
    )


def _read_audit_entries(trail_path: Path) -> list[dict[str, Any]]:
    if not trail_path.is_file():
        return []
    entries: list[dict[str, Any]] = []
    with trail_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


# -- rendering -----------------------------------------------------------------------------


def _chain_to_dict(chain: ChainVerification) -> dict[str, Any]:
    return {"intact": chain.intact, "broken_index": chain.broken_index, "detail": chain.detail}


def bundle_to_dict(bundle: EvidenceBundle) -> dict[str, Any]:
    """Serialize the bundle to a JSON-safe dict (the machine-readable evidence body)."""
    return {
        "telemetry_dir": bundle.telemetry_dir,
        "audit_chain": _chain_to_dict(bundle.audit_chain),
        "audit_entry_count": bundle.audit_entry_count,
        "controls": {
            "well_formed": bundle.controls.well_formed,
            "total": bundle.controls.total,
            "by_framework": bundle.controls.by_framework,
            "control_ids": bundle.controls.control_ids,
            "error": bundle.controls.error,
        },
        "runs": [
            {
                "job_id": run.job_id,
                "cohort_size": run.cohort_size,
                "counts": run.counts,
                "decision_counts": run.decision_counts,
                "slides": [
                    {
                        "slide_stem": s.slide_stem,
                        "outcome": s.outcome,
                        "reason_code": s.reason_code,
                        "detail": s.detail,
                    }
                    for s in run.slides
                ],
                "governance_decisions": [
                    {
                        "action": d.action,
                        "slide_stem": d.slide_stem,
                        "stage": d.stage,
                        "detail": d.detail,
                    }
                    for d in run.governance_decisions
                ],
            }
            for run in bundle.runs
        ],
    }


def render_json(bundle: EvidenceBundle) -> str:
    """Render the bundle as a canonical JSON document (``sort_keys`` for stability)."""
    return json.dumps(bundle_to_dict(bundle), indent=2, sort_keys=True)


def _chain_banner(chain: ChainVerification) -> str:
    if chain.intact:
        return "<p><strong>Audit chain: VERIFIED INTACT</strong></p>"
    detail = html.escape(chain.detail or "verification failed")
    where = (
        "" if chain.broken_index is None else f" (first broken link: entry {chain.broken_index})"
    )
    return f"<p><strong>Audit chain: BROKEN</strong> — {detail}{html.escape(where)}</p>"


def render_html(bundle: EvidenceBundle) -> str:
    """Render the bundle as a self-contained HTML document (no images, no scripts)."""
    parts: list[str] = [
        "<!doctype html>",
        '<meta charset="utf-8">',
        "<title>atlas_conductor compliance evidence</title>",
        "<h1>atlas_conductor compliance evidence bundle</h1>",
        f"<p>telemetry: {html.escape(bundle.telemetry_dir)}</p>",
        _chain_banner(bundle.audit_chain),
        f"<p>audit entries: {bundle.audit_entry_count} &middot; "
        f"control register: {bundle.controls.total} controls "
        f"({'well-formed' if bundle.controls.well_formed else html.escape(bundle.controls.error)})</p>",
    ]
    if not bundle.runs:
        parts.append("<p>No runs recorded.</p>")
    for run in bundle.runs:
        counts_line = "  ".join(f"{o}={n}" for o, n in run.counts.items())
        decisions_line = "  ".join(f"{a}={n}" for a, n in run.decision_counts.items())
        parts.append(f"<h2>run {html.escape(run.job_id)}</h2>")
        parts.append(f"<p>cohort={run.cohort_size} &middot; {html.escape(counts_line)}</p>")
        parts.append(f"<p>governance decisions: {html.escape(decisions_line)}</p>")
        parts.append("<table><thead><tr>")
        parts.append("<th>slide</th><th>verdict</th><th>reason</th><th>detail</th>")
        parts.append("</tr></thead><tbody>")
        for s in run.slides:
            parts.append(
                f"<tr><td>{html.escape(s.slide_stem)}</td>"
                f"<td>{html.escape(s.outcome)}</td>"
                f"<td>{html.escape(s.reason_code)}</td>"
                f"<td>{html.escape(s.detail)}</td></tr>"
            )
        parts.append("</tbody></table>")
        if run.governance_decisions:
            parts.append("<table><thead><tr>")
            parts.append("<th>action</th><th>slide</th><th>stage</th><th>detail</th>")
            parts.append("</tr></thead><tbody>")
            for d in run.governance_decisions:
                parts.append(
                    f"<tr><td>{html.escape(d.action)}</td>"
                    f"<td>{html.escape(d.slide_stem)}</td>"
                    f"<td>{html.escape(d.stage)}</td>"
                    f"<td>{html.escape(d.detail)}</td></tr>"
                )
            parts.append("</tbody></table>")
    return "\n".join(parts)


def export_dossier(
    telemetry_dir: str | Path,
    fmt: str = "json",
    *,
    audit_path: str | Path | None = None,
    registry_path: str | Path | None = None,
) -> str:
    """Build the evidence bundle for ``telemetry_dir`` and render it in ``fmt`` (json|html)."""
    bundle = build_evidence(telemetry_dir, audit_path=audit_path, registry_path=registry_path)
    if fmt == "html":
        return render_html(bundle)
    if fmt == "json":
        return render_json(bundle)
    raise ValueError(f"unknown dossier format {fmt!r} (expected 'json' or 'html')")
