"""Offline training over the recovery dataset (design D-LRC-5).

``train_model`` is a thin, deterministic wrapper: it fits a
:class:`~atlas_conductor.classifier.model.LinearModel` over the featurized recovery dataset
with a fixed seed, so the same telemetry and seed reproduce the artifact. Training is an
explicit, human-invoked, read-only step — no online/continual learning, no auto-retrain.
"""

from __future__ import annotations

from atlas_conductor.classifier.dataset import RecoveryDataset
from atlas_conductor.classifier.model import LinearModel, ModelConfig


def train_model(dataset: RecoveryDataset, seed: int = 0) -> LinearModel:
    """Fit a deterministic ``LinearModel`` from the recovery dataset (fixed seed → reproducible)."""
    return LinearModel.train(dataset.x, dataset.y, ModelConfig(seed=seed))
