"""Evaluation over the recovery dataset (design D-LRC-4/5).

``evaluate`` scores a classifier against a labeled dataset and reports classification
accuracy, per-class precision/recall, and the **safety metric** — the fraction of should-block
rows (rows the rule classifier would block) that the classifier under test would instead
retry. For the composed :class:`~atlas_conductor.classifier.learned.LearnedClassifier` the
safety metric is ``0`` by construction of the monotone-safety gate (design D-LRC-4), and CI
asserts it as a regression guard.
"""

from __future__ import annotations

from typing import Any

from atlas_conductor.classifier import FailureClassifier, RuleClassifier
from atlas_conductor.classifier.dataset import RecoveryDataset
from atlas_conductor.classifier.features import CLASSES
from atlas_conductor.classifier.learned import is_blocking


def evaluate(classifier: FailureClassifier, dataset: RecoveryDataset) -> dict[str, Any]:
    """Score ``classifier`` over ``dataset``; report accuracy, per-class P/R, and safety metric."""
    n = len(dataset)
    rule = RuleClassifier()

    tp = {c: 0 for c in CLASSES}  # true positives per class
    predicted_count = {c: 0 for c in CLASSES}
    actual_count = {c: 0 for c in CLASSES}
    correct = 0
    should_block = 0
    retried_should_block = 0

    for (outcome, verdict), truth_idx in zip(dataset.inputs, dataset.y.tolist(), strict=True):
        truth = CLASSES[int(truth_idx)]
        predicted = classifier.classify(outcome, verdict).classification

        actual_count[truth] += 1
        predicted_count[predicted] += 1
        if predicted is truth:
            correct += 1
            tp[predicted] += 1

        # Safety: rows the rules would block must never be retried by the classifier under test.
        if is_blocking(rule.classify(outcome, verdict).classification):
            should_block += 1
            if not is_blocking(predicted):
                retried_should_block += 1

    per_class = {}
    for c in CLASSES:
        precision = tp[c] / predicted_count[c] if predicted_count[c] else 0.0
        recall = tp[c] / actual_count[c] if actual_count[c] else 0.0
        per_class[c.value] = {"precision": precision, "recall": recall, "support": actual_count[c]}

    return {
        "n": n,
        "accuracy": (correct / n) if n else 0.0,
        "per_class_precision_recall": per_class,
        "safety_metric": (retried_should_block / should_block) if should_block else 0.0,
    }


def format_report(metrics: dict[str, Any]) -> str:
    """Render an evaluation report as human-readable text for the CLI."""
    lines = [
        f"rows: {metrics['n']}",
        f"accuracy: {metrics['accuracy']:.4f}",
        f"safety_metric (should-block rows retried): {metrics['safety_metric']:.4f}",
        "per-class precision / recall:",
    ]
    for cls, pr in metrics["per_class_precision_recall"].items():
        lines.append(
            f"  {cls:<20} precision={pr['precision']:.3f} "
            f"recall={pr['recall']:.3f} support={pr['support']}"
        )
    return "\n".join(lines)
