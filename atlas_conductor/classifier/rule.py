"""The rule-based failure classifier (design D-LRC-1).

This is ``recovery.classify``'s original body, moved verbatim behind the
:class:`~atlas_conductor.classifier.FailureClassifier` seam: hand-written stderr-signature
regexes (CUDA-OOM → resource-transient; missing token / gated encoder → precondition-block)
plus structural verdicts for otherwise-successful invocations, with everything unrecognized
funnelled to ``unknown``. It is the green-in-CI default and the safety floor the learned
classifier can never fall below. Its ``confidence`` is fixed at ``1.0`` — the rules are
deterministic.
"""

from __future__ import annotations

import re

from atlas_conductor.classifier import ClassificationResult
from atlas_conductor.contracts import Classification, Outcome, ReasonCode, Verdict

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


class RuleClassifier:
    """Classify a failure with the hand-written rules (confidence fixed at ``1.0``)."""

    def classify(self, outcome: Outcome | None, verdict: Verdict) -> ClassificationResult:
        classification, signature = self._classify(outcome, verdict)
        return ClassificationResult(classification, signature, confidence=1.0)

    @staticmethod
    def _classify(outcome: Outcome | None, verdict: Verdict) -> tuple[Classification, str]:
        """Classify from the execution outcome and the structural verdict.

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
