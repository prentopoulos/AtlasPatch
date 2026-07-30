"""A compact, deterministic numpy model (design D-LRC-3).

``LinearModel`` is a multinomial logistic regression — a weight matrix + bias over the fixed
feature dimension (:data:`~atlas_conductor.classifier.features.FEATURE_DIM`) and the six
:data:`~atlas_conductor.classifier.features.CLASSES`. Training is deterministic mini-batch
gradient descent with a fixed seed and fixed hyperparameters, so the same dataset and seed
reproduce the artifact byte-for-byte. Inference is a pure numpy ``softmax(x·W + b)``: ``argmax``
is the class, ``max`` is the confidence the abstention floor (design D-LRC-4) keys on. No
runtime clinical reasoning — the deterministic-core invariant holds.

The JSON artifact stores ``{feature_version, classes, weights, bias, config}`` and only that:
learned coefficients indexed by the fixed vocabulary, no stderr text and no slide identifier.
``load`` refuses a ``feature_version`` mismatch so a vocabulary edit can never feed misaligned
features into old weights.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from atlas_conductor.classifier.features import CLASSES, FEATURE_DIM, FEATURE_VERSION
from atlas_conductor.contracts import Classification

N_CLASSES = len(CLASSES)


class FeatureVersionMismatch(ValueError):
    """A model artifact's feature version does not match the running code's vocabulary."""


@dataclass(frozen=True)
class ModelConfig:
    """Fixed training hyperparameters — part of the serialized, reproducible artifact."""

    learning_rate: float = 0.5
    epochs: int = 300
    batch_size: int = 16
    l2: float = 1e-4
    seed: int = 0


def softmax(z: np.ndarray) -> np.ndarray:
    """Row-wise numerically-stable softmax over a ``(n, k)`` score matrix."""
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


@dataclass
class LinearModel:
    """A multinomial logistic-regression classifier over the fixed feature layout."""

    weights: np.ndarray  # (FEATURE_DIM, N_CLASSES)
    bias: np.ndarray  # (N_CLASSES,)
    config: ModelConfig = ModelConfig()
    feature_version: str = FEATURE_VERSION
    classes: tuple[Classification, ...] = CLASSES

    @classmethod
    def train(cls, x: np.ndarray, y: np.ndarray, config: ModelConfig | None = None) -> LinearModel:
        """Fit weights by deterministic mini-batch gradient descent (fixed seed → reproducible).

        ``x`` is ``(n, FEATURE_DIM)``; ``y`` is ``(n,)`` integer class indices into
        :data:`CLASSES`.
        """
        config = config or ModelConfig()
        x = np.asarray(x, dtype=np.float64).reshape(-1, FEATURE_DIM)
        y = np.asarray(y, dtype=np.int64).reshape(-1)
        n = x.shape[0]

        rng = np.random.default_rng(config.seed)
        weights = np.zeros((FEATURE_DIM, N_CLASSES), dtype=np.float64)
        bias = np.zeros(N_CLASSES, dtype=np.float64)
        one_hot = np.eye(N_CLASSES, dtype=np.float64)[y] if n else np.zeros((0, N_CLASSES))

        batch = max(1, config.batch_size)
        for _ in range(config.epochs):
            if n == 0:
                break
            perm = rng.permutation(n)
            for start in range(0, n, batch):
                idx = perm[start : start + batch]
                xb, yb = x[idx], one_hot[idx]
                probs = softmax(xb @ weights + bias)
                grad_z = (probs - yb) / len(idx)
                weights -= config.learning_rate * (xb.T @ grad_z + config.l2 * weights)
                bias -= config.learning_rate * grad_z.sum(axis=0)

        return cls(weights=weights, bias=bias, config=config)

    def predict_proba(self, features_vec: np.ndarray) -> np.ndarray:
        """Softmax class probabilities for one feature vector."""
        vec = np.asarray(features_vec, dtype=np.float64).reshape(1, FEATURE_DIM)
        return softmax(vec @ self.weights + self.bias)[0]

    def predict(self, features_vec: np.ndarray) -> tuple[Classification, float]:
        """Return ``(class, confidence)`` where confidence is the top-class softmax value."""
        probs = self.predict_proba(features_vec)
        index = int(np.argmax(probs))
        return self.classes[index], float(probs[index])

    def to_dict(self) -> dict:
        return {
            "feature_version": self.feature_version,
            "classes": [c.value for c in self.classes],
            "weights": self.weights.tolist(),
            "bias": self.bias.tolist(),
            "config": asdict(self.config),
        }

    def save(self, path: str | Path) -> Path:
        """Serialize the model to a JSON artifact and return its path."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return out

    @classmethod
    def from_dict(cls, data: dict) -> LinearModel:
        version = str(data.get("feature_version", ""))
        if version != FEATURE_VERSION:
            raise FeatureVersionMismatch(
                f"model feature_version {version!r} does not match running code {FEATURE_VERSION!r}"
            )
        classes = tuple(Classification(v) for v in data["classes"])
        return cls(
            weights=np.asarray(data["weights"], dtype=np.float64).reshape(FEATURE_DIM, N_CLASSES),
            bias=np.asarray(data["bias"], dtype=np.float64).reshape(N_CLASSES),
            config=ModelConfig(**data.get("config", {})),
            feature_version=version,
            classes=classes,
        )

    @classmethod
    def load(cls, path: str | Path) -> LinearModel:
        """Load a model artifact; refuse a ``feature_version`` mismatch (design D-LRC-3)."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)
