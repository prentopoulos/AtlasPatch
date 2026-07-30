"""Operational-only, PHI-free feature extraction (tasks 2.1, 2.2)."""

from __future__ import annotations

import numpy as np

from atlas_conductor.classifier.features import (
    CLASSES,
    FEATURE_DIM,
    FEATURE_VERSION,
    STDERR_VOCAB,
    features,
)
from atlas_conductor.contracts import Classification, Outcome, ReasonCode, Verdict

INVALID = Verdict(False, ReasonCode.MISSING_FEATURES, "features missing")

# The identifier a real slide stem / MRN / path fragment might carry — must never survive.
_PLANTED = "PATIENT-MRN-12345-Smith_John"


def test_feature_version_and_class_ordering_are_stable() -> None:
    assert FEATURE_VERSION == "lrc-1"
    assert CLASSES == (
        Classification.RESOURCE_TRANSIENT,
        Classification.PRECONDITION_BLOCK,
        Classification.INPUT_DATA,
        Classification.STRUCTURAL_INVALID,
        Classification.DEPENDENCY_BLOCKED,
        Classification.UNKNOWN,
    )


def test_vector_is_fixed_width_and_binary() -> None:
    vec = features(Outcome(exit_code=1, stderr_tail="CUDA out of memory"), INVALID)
    assert vec.shape == (FEATURE_DIM,)
    assert set(np.unique(vec)).issubset({0.0, 1.0})


def test_oom_token_fires_its_flag() -> None:
    vec = features(Outcome(exit_code=0, stderr_tail="RuntimeError: CUDA out of memory"), INVALID)
    assert vec[STDERR_VOCAB.index("out of memory")] == 1.0
    assert vec[STDERR_VOCAB.index("gated")] == 0.0


def test_absent_outcome_encodes_absent_slots() -> None:
    # No outcome → no stderr flags fire; the vector is still well-formed.
    vec = features(None, INVALID)
    assert vec.shape == (FEATURE_DIM,)
    assert vec[: len(STDERR_VOCAB)].sum() == 0.0


def test_no_planted_identifier_survives_into_the_vector() -> None:
    """PHI-free by construction: an arbitrary identifier in stderr leaves no trace."""
    outcome = Outcome(exit_code=1, stderr_tail=f"Traceback: failure on {_PLANTED}")
    vec = features(outcome, INVALID)
    # The vector is numeric flags only; serializing it can contain no substring of the id.
    serialized = ",".join(str(x) for x in vec.tolist())
    assert _PLANTED not in serialized
    for token in _PLANTED.lower().split("-"):
        if token:
            assert token not in serialized
