"""By-construction governance guardrails over the phase-1 telemetry seam (phase 2).

Every guardrail here is an *additive* filter or gate placed in front of an already
metadata-only phase-1 component (design D17, "Run B"); none changes a phase-1 contract:

* :mod:`atlas_conductor.governance.phi` — pseudonymize a slide stem and detect HIPAA
  Safe-Harbor identifiers (design D20).
* :mod:`atlas_conductor.governance.gate` — :class:`PhiSafeSink`, a ``TelemetrySink``
  decorator that pseudonymizes stems and rejects unneutralizable identifiers before they
  are persisted (design D12/D19).
* :mod:`atlas_conductor.governance.hitl` — the human-in-the-loop confirmation policy and
  the injectable confirmer consulted before an irreversible recovery action (design D13/D21).
* :mod:`atlas_conductor.governance.audit` — a hash-chained, tamper-evident audit trail of
  consequential actions (design D22).

All are pure/deterministic and add no new runtime dependency (stdlib ``hashlib`` + ``re``).
"""

from __future__ import annotations

from atlas_conductor.governance.audit import (
    AuditEntry,
    AuditTrail,
    InMemoryAuditTrail,
    JsonlAuditTrail,
    verify_audit_chain,
)
from atlas_conductor.governance.gate import PhiSafeSink
from atlas_conductor.governance.hitl import (
    AutoApproveConfirmer,
    Confirmer,
    HoldingConfirmer,
    default_confirmer,
    requires_confirmation,
)
from atlas_conductor.governance.phi import pseudonymize_stem, safe_harbor_findings

__all__ = [
    "AuditEntry",
    "AuditTrail",
    "AutoApproveConfirmer",
    "Confirmer",
    "HoldingConfirmer",
    "InMemoryAuditTrail",
    "JsonlAuditTrail",
    "PhiSafeSink",
    "default_confirmer",
    "pseudonymize_stem",
    "requires_confirmation",
    "safe_harbor_findings",
    "verify_audit_chain",
]
