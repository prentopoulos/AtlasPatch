"""The learned classifier's safety floor: confidence + monotone gates (tasks 4.1-4.3)."""

from __future__ import annotations

import numpy as np

from atlas_conductor.classifier import RuleClassifier
from atlas_conductor.classifier.features import FEATURE_DIM, class_index
from atlas_conductor.classifier.learned import LearnedClassifier
from atlas_conductor.classifier.model import N_CLASSES, LinearModel
from atlas_conductor.contracts import Classification, Outcome, ReasonCode, Verdict

INVALID = Verdict(False, ReasonCode.MISSING_FEATURES, "features missing")

# Rule-classified inputs (see RuleClassifier): OOM → resource-transient; gated → precondition;
# unrecognized nonzero exit → unknown.
OOM = Outcome(exit_code=0, stderr_tail="RuntimeError: CUDA out of memory")
PRECONDITION = Outcome(exit_code=1, stderr_tail="gated model requires a Hugging Face token")
MYSTERY = Outcome(exit_code=1, stderr_tail="segfault at 0xdeadbeef")


def _forced_model(target: Classification) -> LinearModel:
    """A model that predicts ``target`` with ~1.0 confidence regardless of input."""
    bias = np.zeros(N_CLASSES)
    bias[class_index(target)] = 30.0
    return LinearModel(weights=np.zeros((FEATURE_DIM, N_CLASSES)), bias=bias)


def _uniform_model() -> LinearModel:
    """All-zero weights and bias → uniform softmax → low confidence (1/6)."""
    return LinearModel(weights=np.zeros((FEATURE_DIM, N_CLASSES)), bias=np.zeros(N_CLASSES))


def test_low_confidence_abstains_to_the_rules() -> None:
    learned = LearnedClassifier(_uniform_model(), threshold=0.6)
    result = learned.classify(OOM, INVALID)
    rule = RuleClassifier().classify(OOM, INVALID)
    assert result.abstained is True
    assert result.classification is rule.classification  # deferred to the rule verdict
    assert result.confidence < 0.6


def test_confident_safe_prediction_is_accepted() -> None:
    # Rule says resource-transient (non-blocking); model confidently agrees → accepted.
    learned = LearnedClassifier(_forced_model(Classification.RESOURCE_TRANSIENT), threshold=0.6)
    result = learned.classify(OOM, INVALID)
    assert result.abstained is False
    assert result.classification is Classification.RESOURCE_TRANSIENT
    assert result.confidence >= 0.6


def test_precondition_block_is_never_upgraded_to_retry() -> None:
    # Model confidently (mis)predicts a retry class for a rule-precondition input.
    learned = LearnedClassifier(_forced_model(Classification.RESOURCE_TRANSIENT), threshold=0.6)
    result = learned.classify(PRECONDITION, INVALID)
    assert result.classification is Classification.PRECONDITION_BLOCK  # still blocking
    assert result.abstained is True


def test_unknown_is_never_upgraded_to_retry() -> None:
    learned = LearnedClassifier(_forced_model(Classification.RESOURCE_TRANSIENT), threshold=0.6)
    result = learned.classify(MYSTERY, INVALID)
    assert result.classification is Classification.UNKNOWN  # still blocking
    assert result.abstained is True


def test_model_may_tighten_a_non_blocking_rule_verdict() -> None:
    # Rule says resource-transient (retry); model says unknown (block) → tightening is allowed.
    learned = LearnedClassifier(_forced_model(Classification.UNKNOWN), threshold=0.6)
    result = learned.classify(OOM, INVALID)
    assert result.classification is Classification.UNKNOWN
    assert result.abstained is False
