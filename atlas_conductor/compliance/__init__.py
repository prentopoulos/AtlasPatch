"""The compliance dossier + run-scoped evidence bundle (phase 7; design D-CMP).

This package assembles a maintained EU AI Act / ISO 42001 dossier *on top of what already
ships* — every claim points at an implemented control and its CI proof — and turns the
standing dossier into per-run conformity evidence. It adds no new runtime dependency and no
new telemetry/audit field: it is a reader over the same PHI-free telemetry/audit path the
GUI and ``export-report`` use (design D-CMP-3).

* :mod:`atlas_conductor.compliance.registry` — the machine-checkable control register
  (``controls.yaml``): the single source of truth for the obligation→control→evidence map
  the dossier renders from (design D-CMP-1).
* :mod:`atlas_conductor.compliance.check` — the CI drift/traceability check that keeps the
  register and ``COMPLIANCE.md`` in lockstep (design D-CMP-2).
* :mod:`atlas_conductor.compliance.evidence` — the run-scoped ``EvidenceBundle`` and its
  JSON/HTML rendering (design D-CMP-3/D-CMP-4).
"""

from __future__ import annotations

from atlas_conductor.compliance.registry import (
    ControlRow,
    default_registry_path,
    load_registry,
)

__all__ = [
    "ControlRow",
    "default_registry_path",
    "load_registry",
]
