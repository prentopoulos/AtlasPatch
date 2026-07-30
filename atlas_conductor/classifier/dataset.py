"""The recovery-dataset reader (design D-LRC-5).

Reads the ``slide_stage_outcomes`` family through the read-only, PHI-free
``TelemetrySink.read_slide_stage_outcomes()`` path (the same one the GUI, ``export-report``,
and ``lineage`` use) and reconstructs a ``(features, label)`` pair per recovery row.

The telemetry is PHI-free, so it never persisted raw stderr — only the derived operational
``signature`` (e.g. ``cuda-oom``, ``structural:nan-features``). Each row is therefore turned
back into a *canonical* :class:`~atlas_conductor.contracts.Outcome`/`Verdict` reconstructed
from its signature — the same operational signal the rules keyed on — and run through the
shared :func:`~atlas_conductor.classifier.features.features` extractor, so training featurizes
exactly as inference does.

Label precedence (design D-LRC-5): the fake-adapter ``injected_label`` ground truth when
present, else the recorded ``classification``; rows with neither a usable signature nor a
label are skipped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from atlas_conductor.classifier.features import CLASSES, FEATURE_DIM, class_index, features
from atlas_conductor.contracts import Classification, Outcome, ReasonCode, Verdict
from atlas_conductor.telemetry import TelemetrySink

# Canonical stderr/exit/reason for each rule signature, so a persisted signature reproduces the
# feature vector its live outcome would have. ``structural:<reason>`` is handled separately.
_CANONICAL: dict[str, tuple[str, int, ReasonCode]] = {
    "cuda-oom": ("cuda out of memory", 0, ReasonCode.MISSING_FEATURES),
    "precondition": (
        "gated model requires a hugging face token (hf_token not set)",
        1,
        ReasonCode.MISSING_FEATURES,
    ),
    "unreadable-input": ("", 0, ReasonCode.UNREADABLE_INPUT),
    "unclassified-nonzero-exit": ("", 1, ReasonCode.MISSING_FEATURES),
    "unclassified": ("", 0, ReasonCode.MISSING),
}

# Ground-truth signature strings (fake-adapter ``injected_label`` values) → the true class.
# Complements ``Classification(value)`` for recorded ``classification`` fields.
_SIGNATURE_TO_CLASS: dict[str, Classification] = {
    "cuda-oom": Classification.RESOURCE_TRANSIENT,
    "precondition": Classification.PRECONDITION_BLOCK,
    "unreadable-input": Classification.INPUT_DATA,
    "input-data": Classification.INPUT_DATA,
    "nan": Classification.STRUCTURAL_INVALID,
    "row_mismatch": Classification.STRUCTURAL_INVALID,
    "row-mismatch": Classification.STRUCTURAL_INVALID,
    "no_coords": Classification.STRUCTURAL_INVALID,
    "no-coords": Classification.STRUCTURAL_INVALID,
    "unclassified": Classification.UNKNOWN,
    "unclassified-nonzero-exit": Classification.UNKNOWN,
}


@dataclass(frozen=True)
class RecoveryDataset:
    """A featurized recovery dataset: aligned feature matrix, labels, and reconstructed inputs."""

    x: np.ndarray  # (n, FEATURE_DIM) feature matrix
    y: np.ndarray  # (n,) class indices into `classes`
    inputs: tuple[tuple[Outcome | None, Verdict], ...]  # per-row reconstructed (outcome, verdict)
    classes: tuple[Classification, ...] = field(default=CLASSES)

    def __len__(self) -> int:
        return int(self.y.shape[0])


def _to_class(value: Any) -> Classification | None:
    """Map a recorded classification value or a signature string to a :class:`Classification`."""
    if not value:
        return None
    text = str(value)
    try:
        return Classification(text)
    except ValueError:
        if text.startswith("structural:"):
            return Classification.STRUCTURAL_INVALID
        return _SIGNATURE_TO_CLASS.get(text)


def _reconstruct(signature: str, attempt: Any) -> tuple[Outcome, Verdict]:
    """Rebuild a canonical (outcome, verdict) from a persisted signature (+ attempt)."""
    attempt_int = int(attempt) if attempt not in (None, "") else None
    if signature.startswith("structural:"):
        reason_value = signature.split(":", 1)[1]
        try:
            reason = ReasonCode(reason_value)
        except ValueError:
            reason = ReasonCode.MISSING
        stderr, exit_code = "", 0
    else:
        stderr, exit_code, reason = _CANONICAL.get(signature, ("", 0, ReasonCode.MISSING))
    outcome = Outcome(exit_code=exit_code, stderr_tail=stderr, attempt=attempt_int)
    return outcome, Verdict(False, reason, "")


def read_dataset(sink: TelemetrySink) -> RecoveryDataset:
    """Read and featurize the recovery dataset from a telemetry sink (read-only)."""
    xs: list[np.ndarray] = []
    ys: list[int] = []
    inputs: list[tuple[Outcome | None, Verdict]] = []
    for row in sink.read_slide_stage_outcomes():
        signature = row.get("signature")
        if not signature:
            continue  # a terminal-outcome row, not a labeled recovery attempt
        label = _to_class(row.get("injected_label")) or _to_class(row.get("classification"))
        if label is None:
            continue
        outcome, verdict = _reconstruct(str(signature), row.get("attempt"))
        xs.append(features(outcome, verdict))
        ys.append(class_index(label))
        inputs.append((outcome, verdict))

    x = np.array(xs, dtype=np.float64) if xs else np.zeros((0, FEATURE_DIM), dtype=np.float64)
    y = np.array(ys, dtype=np.int64)
    return RecoveryDataset(x=x, y=y, inputs=tuple(inputs))
