"""Unit tests for the recovery classifier and action ladder (tasks 6.1, 6.2, 6.3)."""

from __future__ import annotations

from pathlib import Path

from atlas_conductor.contracts import (
    Classification,
    Command,
    Outcome,
    PlanNode,
    ReasonCode,
    RecoveryAction,
    Stage,
    TaskTarget,
    Verdict,
)
from atlas_conductor.recovery import classify, propose

INVALID = Verdict(False, ReasonCode.MISSING_FEATURES, "features missing")
ROW = Verdict(False, ReasonCode.ROW_MISMATCH, "rows differ")


def _node(attempts: int = 1, budget: int = 3, history: tuple[str, ...] = ()) -> PlanNode:
    target = TaskTarget("s", Path("s.svs"), Path("out/patches/s.h5"))
    return PlanNode(
        node_id="n",
        slide_stem="s",
        stage=Stage.EMBED,
        command=Command.PROCESS,
        target=target,
        attempt_budget=budget,
        attempts=attempts,
        mutation_history=history,
    )


# -- classification (6.1) --------------------------------------------------------


def test_oom_is_resource_transient() -> None:
    outcome = Outcome(exit_code=0, stderr_tail="RuntimeError: CUDA out of memory. Tried 2GiB")
    cls, sig = classify(outcome, INVALID)
    assert cls is Classification.RESOURCE_TRANSIENT
    assert sig == "cuda-oom"


def test_missing_token_is_precondition_block() -> None:
    outcome = Outcome(exit_code=1, stderr_tail="OSError: gated model requires a Hugging Face token")
    cls, _ = classify(outcome, INVALID)
    assert cls is Classification.PRECONDITION_BLOCK


def test_row_mismatch_is_structural_invalid() -> None:
    cls, sig = classify(Outcome(exit_code=0), ROW)
    assert cls is Classification.STRUCTURAL_INVALID
    assert "row-mismatch" in sig


def test_unreadable_input_is_input_data() -> None:
    cls, _ = classify(Outcome(exit_code=0), Verdict(False, ReasonCode.UNREADABLE_INPUT, ""))
    assert cls is Classification.INPUT_DATA


def test_unrecognized_nonzero_is_unknown() -> None:
    cls, _ = classify(Outcome(exit_code=1, stderr_tail="segfault at 0xdeadbeef"), INVALID)
    assert cls is Classification.UNKNOWN


# -- action ladder (6.2) ---------------------------------------------------------


def test_oom_retries_with_smaller_batch() -> None:
    p = propose(Classification.RESOURCE_TRANSIENT, "cuda-oom", _node(attempts=1), None)
    assert p.action is RecoveryAction.RETRY_WITH_MUTATION
    assert p.tuning is not None and p.tuning.feature_batch_size == 8


def test_oom_ladder_is_monotone() -> None:
    sizes = []
    for attempt in range(1, 5):
        p = propose(Classification.RESOURCE_TRANSIENT, "cuda-oom", _node(attempts=attempt), None)
        if p.tuning is not None and p.tuning.feature_batch_size is not None:
            sizes.append(p.tuning.feature_batch_size)
    assert sizes == sorted(sizes, reverse=True)  # only ever decreases


def test_oom_budget_exhausted_quarantines() -> None:
    p = propose(Classification.RESOURCE_TRANSIENT, "cuda-oom", _node(attempts=3, budget=3), None)
    assert p.action is RecoveryAction.QUARANTINE_ITEM


def test_structural_forces_then_quarantines() -> None:
    first = propose(Classification.STRUCTURAL_INVALID, "structural:nan", _node(), None)
    assert first.action is RecoveryAction.FORCE_REPROCESS
    after = propose(
        Classification.STRUCTURAL_INVALID,
        "structural:nan",
        _node(history=("force_reprocess",)),
        None,
    )
    assert after.action is RecoveryAction.QUARANTINE_ITEM


def test_precondition_blocks() -> None:
    p = propose(Classification.PRECONDITION_BLOCK, "precondition", _node(), None)
    assert p.action is RecoveryAction.BLOCK_ITEM


# -- unknown never blindly retries (6.3) ----------------------------------------


def test_unknown_blocks_not_retries() -> None:
    outcome = Outcome(exit_code=1, stderr_tail="mystery failure")
    p = propose(Classification.UNKNOWN, "unclassified", _node(), outcome)
    assert p.action is RecoveryAction.BLOCK_ITEM
    assert "mystery failure" in p.detail  # raw stderr surfaced for triage
