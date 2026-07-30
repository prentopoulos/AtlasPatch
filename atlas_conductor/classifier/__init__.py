"""The ``FailureClassifier`` seam (design D-LRC-1).

Recovery classification is routed through a single seam that consumes only the
declarative :class:`~atlas_conductor.contracts.Outcome` and
:class:`~atlas_conductor.contracts.Verdict` contracts and returns a
:class:`ClassificationResult`. Two implementations sit behind it, mirroring the
established real/fake, jsonl/bigquery, and manifest/dvc backend pattern:

- :class:`~atlas_conductor.classifier.rule.RuleClassifier` — today's hand-written rules
  verbatim; the green-in-CI default *and* the safety floor the learned model can never
  fall below.
- :class:`~atlas_conductor.classifier.learned.LearnedClassifier` — an opt-in model learned
  from the PHI-free recovery dataset, gated by the abstention floor so it is never less
  safe than the rules.

``recovery.propose`` consumes ``(classification, signature)`` unchanged; ``confidence`` and
``abstained`` are used only by the seam's abstention logic, never by the action ladder.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from atlas_conductor.contracts import Classification, Outcome, Verdict


@dataclass(frozen=True)
class ClassificationResult:
    """The result of classifying a failure through the seam (design D-LRC-1).

    ``confidence`` is ``1.0`` for the deterministic rules; for a learned classifier it is the
    top-class softmax probability. ``abstained`` is set when a learned classifier fell back to
    the rule result (low confidence or a safety-gate violation), with the learned ``signature``
    preserved for telemetry.
    """

    classification: Classification
    signature: str
    confidence: float
    abstained: bool = False


@runtime_checkable
class FailureClassifier(Protocol):
    """The single classification seam every failure is routed through."""

    def classify(self, outcome: Outcome | None, verdict: Verdict) -> ClassificationResult:
        ...


# Re-exported at the bottom to avoid a circular import: ``rule`` imports ``ClassificationResult``
# from this module, so the dataclass/protocol must be defined before that import runs.
from atlas_conductor.classifier.rule import RuleClassifier  # noqa: E402

__all__ = ["ClassificationResult", "FailureClassifier", "RuleClassifier"]
