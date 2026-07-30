"""Operational-only, PHI-free feature extraction (design D-LRC-2).

Features are drawn *only* from operational signals — presence of tokens from a fixed
operational stderr vocabulary, the structural verdict reason code, the exit-code sign, and
the attempt bucket — and never from slide pixels, embeddings, raw free-text stderr, slide
stems, or filesystem paths. The model is therefore metadata-only and PHI-free **by
construction**: the vector is a bag of bounded flags, and the serialized model holds only
coefficients indexed by this fixed vocabulary, so no stderr string ever survives training.

The vocabulary carries a :data:`FEATURE_VERSION`; a model trained under one version refuses
to load against another (design D-LRC-3), so a vocabulary edit can never silently misalign
weights. :data:`CLASSES` is the fixed output-class ordering shared by the model, the dataset
reader, and the safety gate.
"""

from __future__ import annotations

import numpy as np

from atlas_conductor.contracts import Classification, Outcome, ReasonCode, Verdict

# Bump whenever the vocabulary, the class ordering, or the vector layout below changes.
FEATURE_VERSION = "lrc-1"

# The fixed output-class ordering (the six-member failure taxonomy). Shared by the model's
# output dimension, the dataset reader's label index, and the safety gate's rank map.
CLASSES: tuple[Classification, ...] = (
    Classification.RESOURCE_TRANSIENT,
    Classification.PRECONDITION_BLOCK,
    Classification.INPUT_DATA,
    Classification.STRUCTURAL_INVALID,
    Classification.DEPENDENCY_BLOCKED,
    Classification.UNKNOWN,
)

# Bounded operational stderr vocabulary — the same class of signal the rule regexes key on
# (design D-LRC-2). Matched case-insensitively as substrings of ``stderr_tail``. Never an
# unbounded/TF-IDF vocabulary, so no path fragment or identifier can enter the model.
STDERR_VOCAB: tuple[str, ...] = (
    "cuda",
    "out of memory",
    "cuda_error_out_of_memory",
    "hf_token",
    "huggingface",
    "gated",
    "401",
    "unauthorized",
    "token is required",
    "access to model",
    "could not find model",
    "no module named",
    "not installed",
    "traceback",
    "killed",
    "timeout",
    "segfault",
    "runtimeerror",
    "oserror",
)

# The ReasonCode one-hot ordering (stable by enum definition order).
REASON_CODES: tuple[ReasonCode, ...] = tuple(ReasonCode)

# Exit-code sign one-hot: [absent, zero, nonzero]. Attempt bucket one-hot: [absent, 1st, 2nd, 3rd+].
_EXITCODE_SLOTS = 3
_ATTEMPT_SLOTS = 4

# The total feature dimension — the fixed layout the model's weight matrix is indexed by.
FEATURE_DIM = len(STDERR_VOCAB) + len(REASON_CODES) + _EXITCODE_SLOTS + _ATTEMPT_SLOTS


def features(outcome: Outcome | None, verdict: Verdict) -> np.ndarray:
    """Extract the fixed-layout operational feature vector for one failure (design D-LRC-2).

    Layout: ``[stderr-token flags | reason-code one-hot | exit-code sign | attempt bucket]``.
    All values are 0/1; no free text ever enters the vector.
    """
    vec = np.zeros(FEATURE_DIM, dtype=np.float64)
    offset = 0

    # Bernoulli presence flags over the fixed stderr vocabulary (case-insensitive substring).
    stderr = (outcome.stderr_tail if outcome is not None else "").lower()
    for i, token in enumerate(STDERR_VOCAB):
        if token in stderr:
            vec[offset + i] = 1.0
    offset += len(STDERR_VOCAB)

    # One-hot of the structural verdict reason code.
    vec[offset + REASON_CODES.index(verdict.reason)] = 1.0
    offset += len(REASON_CODES)

    # Exit-code sign: absent (no outcome) / zero / nonzero.
    if outcome is None:
        vec[offset + 0] = 1.0
    elif outcome.exit_code == 0:
        vec[offset + 1] = 1.0
    else:
        vec[offset + 2] = 1.0
    offset += _EXITCODE_SLOTS

    # Attempt bucket: absent / first / second / third-or-later.
    attempt = outcome.attempt if outcome is not None else None
    if attempt is None:
        vec[offset + 0] = 1.0
    elif attempt <= 1:
        vec[offset + 1] = 1.0
    elif attempt == 2:
        vec[offset + 2] = 1.0
    else:
        vec[offset + 3] = 1.0

    return vec


def class_index(classification: Classification) -> int:
    """Index of a classification in the fixed :data:`CLASSES` ordering."""
    return CLASSES.index(classification)
