"""The PHI-free telemetry write-gate (tasks 1.2; design D12/D19).

:class:`PhiSafeSink` decorates any :class:`~atlas_conductor.telemetry.TelemetrySink`. The
``TelemetrySink`` ABC is the single write chokepoint for every component, so wrapping it
once (at the run façade, ``run.py``) makes the gate universal and backend-agnostic — the
same gate protects the phase-4 BigQuery backend for free — while leaving the phase-1 sinks
untouched (design D19). Per record, in a fixed order (design D20):

1. **Pseudonymize** the ``slide_stem`` — a stem may itself be an MRN or accession number,
   so it is replaced with a stable per-run token before the record is persisted. This is
   the primary control; the common case (a stem that is an identifier) is neutralized, not
   rejected, so real cohorts stay processable.
2. **Scan** the free-text fields (``detail``) for a HIPAA Safe-Harbor identifier shape that
   pseudonymization does not reach — for example a raw stderr tail folded into a recovery
   detail. Any hit **fails closed**: the record is dropped, the run continues, and the
   rejection is recorded in the audit trail (naming the *shapes* found, never the value).
3. **Delegate** the pseudonymized, scanned record to the inner sink.

Config paths the operator supplied (``input_dir``, output paths) and bounded enums are not
scanned for rejection — rejecting the operator's own output path would be absurd; the leak
risk is the free-text tails (design D20).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any, TypeVar

from atlas_conductor.governance.audit import AuditTrail
from atlas_conductor.governance.phi import is_pseudonym, pseudonymize_stem, safe_harbor_findings
from atlas_conductor.telemetry import (
    AgentEventRecord,
    JobRecord,
    MessageFlowRecord,
    SlideStageOutcomeRecord,
    TelemetrySink,
    ValidationResultRecord,
)

# Free-text fields that may carry an identifier pseudonymization does not reach.
_SCANNED_FIELDS: tuple[str, ...] = ("detail",)

_R = TypeVar("_R")


class PhiGateRejection(Exception):
    """Internal signal that a record carried an unneutralizable Safe-Harbor identifier."""


class PhiSafeSink(TelemetrySink):
    """A ``TelemetrySink`` decorator enforcing the PHI-free write invariant (design D12)."""

    def __init__(self, inner: TelemetrySink, audit: AuditTrail | None = None) -> None:
        self._inner = inner
        self._audit = audit

    # -- write path (gated) ------------------------------------------------------

    def record_job(self, record: JobRecord) -> None:
        self._guard(record, self._inner.record_job)

    def record_slide_stage_outcome(self, record: SlideStageOutcomeRecord) -> None:
        self._guard(record, self._inner.record_slide_stage_outcome)

    def record_validation(self, record: ValidationResultRecord) -> None:
        self._guard(record, self._inner.record_validation)

    def record_agent_event(self, record: AgentEventRecord) -> None:
        self._guard(record, self._inner.record_agent_event)

    def record_message_flow(self, record: MessageFlowRecord) -> None:
        # The generic ``_guard`` path pseudonymizes ``slide_stem`` and scans ``detail`` the
        # same way as every other family, so the new family is gated with no special-casing.
        self._guard(record, self._inner.record_message_flow)

    def _guard(self, record: _R, delegate: Callable[[_R], None]) -> None:
        safe = self._pseudonymize(record)
        findings = self._scan(safe)
        if findings:
            self._reject(safe, findings)
            return
        delegate(safe)

    # -- gate steps --------------------------------------------------------------

    @staticmethod
    def _pseudonymize(record: _R) -> _R:
        """Return ``record`` with its ``slide_stem`` replaced by a per-run pseudonym."""
        stem = getattr(record, "slide_stem", None)
        if not stem or is_pseudonym(stem):
            return record
        job_id = getattr(record, "job_id", "")
        return replace(record, slide_stem=pseudonymize_stem(stem, job_id))  # type: ignore[type-var]

    @staticmethod
    def _scan(record: Any) -> dict[str, list[str]]:
        """Map each scanned field to the Safe-Harbor shapes it carries (empty if clean)."""
        findings: dict[str, list[str]] = {}
        for field in _SCANNED_FIELDS:
            value = getattr(record, field, None)
            if isinstance(value, str):
                shapes = safe_harbor_findings(value)
                if shapes:
                    findings[field] = shapes
        return findings

    def _reject(self, record: Any, findings: dict[str, list[str]]) -> None:
        """Drop the record (fail closed) and record the rejection in the audit trail."""
        if self._audit is not None:
            shapes = sorted({shape for shapes in findings.values() for shape in shapes})
            self._audit.append(
                "phi-gate-rejection",
                {
                    "job_id": getattr(record, "job_id", ""),
                    "slide_stem": getattr(record, "slide_stem", None),
                    "record_type": type(record).__name__,
                    # Comma-joined so the audit payload stays scalar-only (no array can be
                    # recorded); names the *fields* and *shapes*, never the matched value.
                    "fields": ",".join(sorted(findings)),
                    "shapes": ",".join(shapes),
                },
            )

    # -- read path (delegated) ---------------------------------------------------

    def read_agent_events(self) -> list[dict[str, Any]]:
        return self._inner.read_agent_events()

    def read_slide_stage_outcomes(self) -> list[dict[str, Any]]:
        return self._inner.read_slide_stage_outcomes()

    def read_message_flow(self) -> list[dict[str, Any]]:
        return self._inner.read_message_flow()
