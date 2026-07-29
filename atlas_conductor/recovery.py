"""The recovery agent (tasks 6.1, 6.2, 6.3; slice A3).

Recovery is a pure classifier and proposer (design D6): it classifies a failure from
two sources — the worker's raw execution outcome and the validator's structural verdict
— into the bounded taxonomy, and proposes a plan-delta drawn only from AtlasPatch's own
tuning knobs (design D7). It never mutates plan state; the planner integrates the
proposal as the single writer (task 4.4).

Three invariants live here:
- **Two-source classification (6.1):** stderr-signature matching for execution failures
  (CUDA-OOM → resource-transient; missing token / gated encoder → precondition-block),
  and structural verdicts for otherwise-successful invocations (row mismatch / NaN /
  missing output → structural-invalid).
- **Bounded, monotone action ladder (6.2):** ``retry_with_mutation`` walks a ladder
  whose tuning values only decrease, bounded by the per-item attempt budget; a
  structural-invalid slide is rebuilt once with ``force_reprocess`` and then quarantined.
- **Unknown → block (6.3):** an unrecognized failure is never blindly retried; it is
  blocked and its raw stderr tail is surfaced for human triage.

The HITL confirmation gate on the irreversible actions (force / quarantine / block) is
phase 2 (design D13); phase-1 recovery proposes and the planner applies them within the
attempt budget.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from atlas_conductor.contracts import (
    Classification,
    Outcome,
    PlanNode,
    ReasonCode,
    RecoveryAction,
    Tuning,
    Verdict,
)

# stderr signatures (design D3: stderr is a classification hint, never a success signal).
_OOM_RE = re.compile(r"cuda out of memory|out of memory|CUDA_ERROR_OUT_OF_MEMORY", re.IGNORECASE)
_PRECONDITION_RE = re.compile(
    r"huggingface|hf_token|gated|401 client error|unauthorized|could not find model|"
    r"access to model|token is required|not installed|no module named",
    re.IGNORECASE,
)

# Structural verdict reasons that mean the invocation ran but produced bad output.
_STRUCTURAL_REASONS = frozenset(
    {
        ReasonCode.ROW_MISMATCH,
        ReasonCode.NAN_FEATURES,
        ReasonCode.MISSING_FEATURES,
        ReasonCode.NO_COORDS,
        ReasonCode.CORRUPT,
        ReasonCode.MISSING,
    }
)

# The monotone mutation ladder: each rung only *lowers* resource pressure (design D7).
_LADDER: tuple[Tuning, ...] = (
    Tuning(feature_batch_size=8, seg_batch_size=1, max_open_slides=4),
    Tuning(feature_batch_size=4, seg_batch_size=1, max_open_slides=2),
    Tuning(feature_batch_size=2, seg_batch_size=1, max_open_slides=1),
    Tuning(feature_batch_size=1, seg_batch_size=1, max_open_slides=1, feature_precision="fp16"),
)


@dataclass(frozen=True)
class RecoveryProposal:
    """A classification plus a proposed plan-delta (design D6). The planner applies it."""

    classification: Classification
    action: RecoveryAction
    signature: str
    tuning: Tuning | None = None  # new tuning for a retry_with_mutation
    detail: str = ""


def classify(outcome: Outcome | None, verdict: Verdict) -> tuple[Classification, str]:
    """Classify a failure from the execution outcome and the structural verdict.

    Returns ``(classification, signature)`` where the signature is a short label used in
    the labeled recovery dataset (design D14).
    """
    stderr = outcome.stderr_tail if outcome is not None else ""
    if _OOM_RE.search(stderr):
        return Classification.RESOURCE_TRANSIENT, "cuda-oom"
    if _PRECONDITION_RE.search(stderr):
        return Classification.PRECONDITION_BLOCK, "precondition"

    if verdict.reason is ReasonCode.UNREADABLE_INPUT:
        return Classification.INPUT_DATA, "unreadable-input"

    # A nonzero exit with no recognized signature is an unrecognized *process* failure
    # (e.g. a crash): treat it as unknown and block rather than trusting the structural
    # verdict and force-retrying (design D3/6.3). Only when the process claims success
    # (exit 0) do we attribute a bad-output verdict to a structural cause.
    if outcome is not None and outcome.exit_code != 0:
        return Classification.UNKNOWN, "unclassified-nonzero-exit"

    if verdict.reason in _STRUCTURAL_REASONS:
        return Classification.STRUCTURAL_INVALID, f"structural:{verdict.reason.value}"
    return Classification.UNKNOWN, "unclassified"


def propose(
    classification: Classification, signature: str, node: PlanNode, outcome: Outcome | None
) -> RecoveryProposal:
    """Propose a bounded recovery action for a classified failure (design D7)."""
    attempts_left = node.attempt_budget - node.attempts

    if classification is Classification.RESOURCE_TRANSIENT:
        if attempts_left > 0:
            rung = max(0, node.attempts - 1)  # first retry (1 attempt done) → mildest rung
            return RecoveryProposal(
                classification,
                RecoveryAction.RETRY_WITH_MUTATION,
                signature,
                tuning=_ladder_rung(rung),
                detail=f"reduce batch/open-slides (rung {min(rung, len(_LADDER) - 1)})",
            )
        return RecoveryProposal(
            classification,
            RecoveryAction.QUARANTINE_ITEM,
            signature,
            detail="attempt budget exhausted",
        )

    if classification is Classification.STRUCTURAL_INVALID:
        # Rebuild once with --force; if it is still invalid, quarantine (spec scenario).
        if "force_reprocess" not in node.mutation_history and attempts_left > 0:
            return RecoveryProposal(
                classification,
                RecoveryAction.FORCE_REPROCESS,
                signature,
                tuning=Tuning(force=True),
                detail="rebuild once with --force",
            )
        return RecoveryProposal(
            classification,
            RecoveryAction.QUARANTINE_ITEM,
            signature,
            detail="still structurally invalid after force-reprocess",
        )

    if classification is Classification.PRECONDITION_BLOCK:
        return RecoveryProposal(
            classification,
            RecoveryAction.BLOCK_ITEM,
            signature,
            detail="precondition not satisfiable via tuning (e.g. missing token/encoder)",
        )

    if classification is Classification.INPUT_DATA:
        return RecoveryProposal(
            classification,
            RecoveryAction.BLOCK_ITEM,
            signature,
            detail="input data not processable",
        )

    # UNKNOWN (and any residual): never blind-retry — block and surface the stderr tail.
    tail = (outcome.stderr_tail[-500:] if outcome is not None else "").strip()
    return RecoveryProposal(
        classification,
        RecoveryAction.BLOCK_ITEM,
        signature,
        detail=f"unclassified failure; stderr tail: {tail}" if tail else "unclassified failure",
    )


def _ladder_rung(attempt_index: int) -> Tuning:
    """Return the monotone tuning for the given prior-attempt count."""
    return _LADDER[min(attempt_index, len(_LADDER) - 1)]
