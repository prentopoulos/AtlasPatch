"""The deterministic numpy model: training, inference, serialization (tasks 3.1, 3.2)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from atlas_conductor.classifier.features import CLASSES, FEATURE_DIM
from atlas_conductor.classifier.model import (
    N_CLASSES,
    FeatureVersionMismatch,
    LinearModel,
    ModelConfig,
    softmax,
)


def _synthetic(seed: int = 0):
    """A small linearly-separable dataset: one distinct feature slot per class."""
    rng = np.random.default_rng(seed)
    rows, labels = [], []
    for _ in range(30):
        for cls_idx in range(N_CLASSES):
            vec = np.zeros(FEATURE_DIM)
            vec[cls_idx] = 1.0  # a class-distinctive flag
            vec[N_CLASSES + rng.integers(0, 3)] = 1.0  # a little noise
            rows.append(vec)
            labels.append(cls_idx)
    return np.array(rows), np.array(labels)


def test_softmax_rows_sum_to_one() -> None:
    p = softmax(np.array([[1.0, 2.0, 3.0], [0.0, 0.0, 0.0]]))
    assert np.allclose(p.sum(axis=1), 1.0)


def test_model_learns_a_separable_dataset() -> None:
    x, y = _synthetic()
    model = LinearModel.train(x, y)
    correct = sum(CLASSES.index(model.predict(x[i])[0]) == y[i] for i in range(len(y)))
    assert correct / len(y) >= 0.95


def test_predict_returns_class_and_confidence() -> None:
    x, y = _synthetic()
    model = LinearModel.train(x, y)
    cls, conf = model.predict(x[0])
    assert cls in CLASSES
    assert 0.0 <= conf <= 1.0


def test_training_is_deterministic() -> None:
    x, y = _synthetic()
    a = LinearModel.train(x, y, ModelConfig(seed=7))
    b = LinearModel.train(x, y, ModelConfig(seed=7))
    assert np.array_equal(a.weights, b.weights)
    assert np.array_equal(a.bias, b.bias)
    assert a.to_dict() == b.to_dict()


def test_json_round_trip(tmp_path: Path) -> None:
    x, y = _synthetic()
    model = LinearModel.train(x, y)
    path = model.save(tmp_path / "model.json")
    loaded = LinearModel.load(path)
    assert np.array_equal(model.weights, loaded.weights)
    assert np.array_equal(model.bias, loaded.bias)
    assert loaded.classes == CLASSES
    # Predictions are identical after a round trip.
    for i in range(len(y)):
        assert model.predict(x[i]) == loaded.predict(x[i])


def test_load_refuses_feature_version_mismatch(tmp_path: Path) -> None:
    x, y = _synthetic()
    path = LinearModel.train(x, y).save(tmp_path / "model.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["feature_version"] = "some-other-version"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(FeatureVersionMismatch):
        LinearModel.load(path)
