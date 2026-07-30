"""The learned classifier and its safety floor (design D-LRC-4).

``LearnedClassifier`` composes a :class:`~atlas_conductor.classifier.model.LinearModel` with a
rule-based fallback and enforces two gates before ever returning a learned class, so it is
**provably never less safe than the rules**:

1. **Confidence gate** — if the top-class softmax confidence is below ``threshold``, abstain
   and return the rule result (learned signature preserved, ``abstained=True``).
2. **Monotone-safety gate** — map each classification to a permissiveness rank
   (block-class < quarantine-class < retry-class). When the rule classifier assigns a
   *blocking* class (``precondition-block``, ``input-data``, ``unknown``, or the residual
   ``dependency-blocked``), the learned class may not be *more* permissive; a violation
   abstains to the rule result.

Together these preserve the "unknown/precondition → block, never blind-retry" invariant
(failure-recovery spec) for *any* trained weights, including a pathologically bad model.
"""

from __future__ import annotations

from atlas_conductor.classifier import ClassificationResult, FailureClassifier, RuleClassifier
from atlas_conductor.classifier.features import features
from atlas_conductor.classifier.model import LinearModel
from atlas_conductor.contracts import Classification, Outcome, Verdict

# Permissiveness rank: how retryable a classification's downstream action is (design D-LRC-4).
# Blocking classes propose ``block_item`` (rank 0); ``structural-invalid`` force-reprocesses
# once (rank 1); ``resource-transient`` retries (rank 2). Higher = more permissive.
PERMISSIVENESS: dict[Classification, int] = {
    Classification.PRECONDITION_BLOCK: 0,
    Classification.INPUT_DATA: 0,
    Classification.UNKNOWN: 0,
    Classification.DEPENDENCY_BLOCKED: 0,
    Classification.STRUCTURAL_INVALID: 1,
    Classification.RESOURCE_TRANSIENT: 2,
}

# The classes whose downstream action blocks (never retries) — the safety floor's trigger set.
BLOCKING_CLASSES: frozenset[Classification] = frozenset(
    c for c, rank in PERMISSIVENESS.items() if rank == 0
)

DEFAULT_THRESHOLD = 0.6


def permissiveness_rank(classification: Classification) -> int:
    return PERMISSIVENESS[classification]


def is_blocking(classification: Classification) -> bool:
    """True when the classification's downstream action blocks rather than retries."""
    return classification in BLOCKING_CLASSES


class LearnedClassifier:
    """A learned classifier gated by the rule-based safety floor (design D-LRC-4)."""

    def __init__(
        self,
        model: LinearModel,
        fallback: FailureClassifier | None = None,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        self._model = model
        self._fallback: FailureClassifier = fallback or RuleClassifier()
        self._threshold = threshold

    def classify(self, outcome: Outcome | None, verdict: Verdict) -> ClassificationResult:
        rule = self._fallback.classify(outcome, verdict)
        predicted, confidence = self._model.predict(features(outcome, verdict))
        signature = f"learned:{predicted.value}"

        # Confidence gate: an underconfident model degrades to the rules, not below them.
        if confidence < self._threshold:
            return ClassificationResult(rule.classification, signature, confidence, abstained=True)

        # Monotone-safety gate: never loosen a rule-blocked failure into a more permissive class.
        if is_blocking(rule.classification) and permissiveness_rank(
            predicted
        ) > permissiveness_rank(rule.classification):
            return ClassificationResult(rule.classification, signature, confidence, abstained=True)

        return ClassificationResult(predicted, signature, confidence, abstained=False)
