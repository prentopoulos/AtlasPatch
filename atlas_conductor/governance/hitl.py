"""Human-in-the-loop confirmation gate (tasks 3.1; design D13/D21).

HITL belongs exactly where an action is irreversible or expensive, not on every decision
(design D13). Two pieces:

* :func:`requires_confirmation` — a *pure* policy over the recovery action alone (no slide
  content, timing, or environment), so the gate is deterministic, testable, and matches the
  System Card's HITL table exactly.
* :class:`Confirmer` — an injectable mechanism the scheduler consults *only* when the policy
  says a hold is needed. :class:`HoldingConfirmer` is the safe attended default (an
  irreversible action never runs without a human "yes"); :class:`AutoApproveConfirmer` is
  used under an explicit unattended waiver. Separating policy from mechanism keeps the
  decision auditable and lets CI drive both branches with no human.

The gate is installed at the run façade (design D21): the scheduler defaults to
auto-approve (no gate) so its unit tests stay ungated, while ``run_job`` selects the real
confirmer from ``JobConfig.unattended``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from atlas_conductor.contracts import RecoveryAction

# The irreversible or expensive actions that require human confirmation (design D13):
# force_reprocess overwrites outputs, block_job terminates the run, quarantine_item sets
# an item aside. Every other action is bounded and non-destructive and stays autonomous.
_CONFIRMATION_REQUIRED: frozenset[RecoveryAction] = frozenset(
    {
        RecoveryAction.FORCE_REPROCESS,
        RecoveryAction.BLOCK_JOB,
        RecoveryAction.QUARANTINE_ITEM,
    }
)


def requires_confirmation(action: RecoveryAction) -> bool:
    """True if ``action`` is irreversible/expensive and must be confirmed before applying."""
    return action in _CONFIRMATION_REQUIRED


@runtime_checkable
class Confirmer(Protocol):
    """Decides whether a gated action may proceed. Consulted only when the policy holds."""

    def confirm(self, action: RecoveryAction, slide_stem: str, detail: str) -> bool:
        """Return True to apply the action, False to hold it."""
        ...


class AutoApproveConfirmer(Confirmer):
    """Approves every gated action — used under an explicit unattended waiver."""

    def confirm(self, action: RecoveryAction, slide_stem: str, detail: str) -> bool:
        return True


class HoldingConfirmer(Confirmer):
    """Holds every gated action — the safe attended default when no human can answer.

    In a non-interactive context (such as CI) confirmation is unavailable, so the action is
    held rather than taken; the scheduler records the held state so nothing is lost.
    """

    def confirm(self, action: RecoveryAction, slide_stem: str, detail: str) -> bool:
        return False


def default_confirmer(unattended: bool) -> Confirmer:
    """Select the confirmer for a run: auto-approve when unattended, else hold."""
    confirmer: Confirmer = AutoApproveConfirmer() if unattended else HoldingConfirmer()
    return confirmer
