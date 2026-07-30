"""The `FailureClassifier` seam: the rule default is behavior-identical (tasks 1.1-1.3)."""

from __future__ import annotations

from pathlib import Path

from atlas_conductor.classifier import ClassificationResult, FailureClassifier, RuleClassifier
from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import (
    Classification,
    Geometry,
    Outcome,
    ReasonCode,
    RequestedOutput,
    SlideOutcome,
    Verdict,
)
from atlas_conductor.dispatch import FakeAdapter, Injection
from atlas_conductor.planning import Planner
from atlas_conductor.recovery import classify
from atlas_conductor.scheduler import Scheduler
from atlas_conductor.telemetry import InMemoryTelemetrySink

INVALID = Verdict(False, ReasonCode.MISSING_FEATURES, "features missing")
ROW = Verdict(False, ReasonCode.ROW_MISMATCH, "rows differ")
UNREADABLE = Verdict(False, ReasonCode.UNREADABLE_INPUT, "")

# A representative matrix spanning every branch of the rules.
_CASES = [
    (Outcome(exit_code=0, stderr_tail="RuntimeError: CUDA out of memory"), INVALID),
    (Outcome(exit_code=1, stderr_tail="gated model requires a Hugging Face token"), INVALID),
    (Outcome(exit_code=0), ROW),
    (Outcome(exit_code=0), UNREADABLE),
    (Outcome(exit_code=1, stderr_tail="segfault at 0xdeadbeef"), INVALID),
    (None, INVALID),
]


def test_rule_classifier_is_a_failure_classifier() -> None:
    assert isinstance(RuleClassifier(), FailureClassifier)


def test_rule_classifier_matches_recovery_classify() -> None:
    rule = RuleClassifier()
    for outcome, verdict in _CASES:
        result = rule.classify(outcome, verdict)
        assert isinstance(result, ClassificationResult)
        # The seam reproduces the wrapper's (classification, signature) exactly.
        assert (result.classification, result.signature) == classify(outcome, verdict)
        assert result.confidence == 1.0  # deterministic rules
        assert result.abstained is False


def _config(cohort: Path, out: Path) -> JobConfig:
    return JobConfig(
        input_dir=cohort,
        output_dir=out,
        requested_output=RequestedOutput.FEATURES,
        geometry=Geometry(patch_size=256, target_mag=20),
        encoders=("resnet50",),
    )


def _cohort(tmp_path: Path) -> Path:
    cohort = tmp_path / "cohort"
    cohort.mkdir(parents=True, exist_ok=True)
    (cohort / "s.svs").write_bytes(b"fake-wsi")
    return cohort


def test_default_scheduler_routes_through_the_rules(tmp_path: Path) -> None:
    """A default scheduler (no classifier passed) classifies via the rule-based seam."""
    config = _config(_cohort(tmp_path), tmp_path / "out")
    telemetry = InMemoryTelemetrySink()
    adapter = FakeAdapter(
        injections={"s": Injection("oom", fail_until_attempt=1, label="cuda-oom")}
    )

    plan = Planner(telemetry).build_plan(config)
    result = Scheduler(config, adapter, telemetry).run(plan)  # default classifier

    assert result.count(SlideOutcome.VALID) == 1
    recoveries = [r for r in telemetry.slide_stage_outcomes if r.classification is not None]
    assert recoveries and recoveries[0].classification == Classification.RESOURCE_TRANSIENT.value
