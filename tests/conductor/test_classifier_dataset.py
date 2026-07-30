"""Dataset reader + train/eval over a fake-adapter recovery dataset (tasks 5.1-5.3)."""

from __future__ import annotations

from pathlib import Path

from atlas_conductor.classifier.dataset import read_dataset
from atlas_conductor.classifier.evaluate import evaluate
from atlas_conductor.classifier.learned import LearnedClassifier
from atlas_conductor.classifier.rule import RuleClassifier
from atlas_conductor.classifier.train import train_model
from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import Geometry, RequestedOutput
from atlas_conductor.dispatch import FakeAdapter, Injection
from atlas_conductor.planning import Planner
from atlas_conductor.scheduler import Scheduler
from atlas_conductor.telemetry import InMemoryTelemetrySink

GEO = Geometry(patch_size=256, target_mag=20)


def _build_recovery_telemetry(tmp_path: Path) -> InMemoryTelemetrySink:
    """Run a mixed cohort of injected failures to accumulate a labeled recovery dataset."""
    cohort = tmp_path / "cohort"
    cohort.mkdir(parents=True, exist_ok=True)
    injections: dict[str, Injection] = {}
    # A spread of failure modes across many slides so every class is represented.
    plan = [("oom", "cuda-oom", 12), ("precondition", "precondition", 12), ("nan", "nan", 12)]
    idx = 0
    for mode, label, count in plan:
        for _ in range(count):
            stem = f"s{idx}"
            (cohort / f"{stem}.svs").write_bytes(b"fake-wsi")
            # A transient OOM resolves on retry; the others persist to a terminal action.
            injections[stem] = Injection(
                mode, fail_until_attempt=1 if mode == "oom" else 1_000_000, label=label
            )
            idx += 1

    config = JobConfig(
        input_dir=cohort,
        output_dir=tmp_path / "out",
        requested_output=RequestedOutput.FEATURES,
        geometry=GEO,
        encoders=("resnet50",),
    )
    telemetry = InMemoryTelemetrySink()
    scheduler = Scheduler(config, FakeAdapter(injections=injections), telemetry)
    scheduler.run(Planner(telemetry).build_plan(config))
    return telemetry


def test_dataset_reads_labeled_recovery_rows(tmp_path: Path) -> None:
    telemetry = _build_recovery_telemetry(tmp_path)
    dataset = read_dataset(telemetry)
    assert len(dataset) > 0
    assert dataset.x.shape[0] == len(dataset) == dataset.y.shape[0]
    # More than one class present (oom → resource-transient, precondition, structural).
    assert len(set(dataset.y.tolist())) >= 2


def test_training_is_deterministic_from_telemetry(tmp_path: Path) -> None:
    dataset = read_dataset(_build_recovery_telemetry(tmp_path))
    a = train_model(dataset, seed=0)
    b = train_model(dataset, seed=0)
    assert a.to_dict() == b.to_dict()


def test_learned_classifier_is_accurate_and_safe(tmp_path: Path) -> None:
    dataset = read_dataset(_build_recovery_telemetry(tmp_path))
    model = train_model(dataset, seed=0)
    learned = LearnedClassifier(model, fallback=RuleClassifier(), threshold=0.6)

    metrics = evaluate(learned, dataset)
    assert metrics["accuracy"] >= 0.9  # relearns the rule labels on this separable data
    assert metrics["safety_metric"] == 0.0  # composed floor never retries a should-block row
