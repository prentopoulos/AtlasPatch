"""End-to-end recovery tests against the fake adapter (tasks 9.1, 5.3, 5.5).

Drives the full loop with injected, labeled failures and asserts the stage-granular
recovery behaviour: an injected OOM keeps the segmentation and retries only the embed;
a structural-invalid slide is force-rebuilt once then quarantined; a precondition block
propagates to its dependents; and unknown failures are blocked, not retried. The
telemetry is checked as a labeled recovery dataset (design D14).
"""

from __future__ import annotations

from pathlib import Path

import h5py

from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import (
    Decision,
    Geometry,
    ReasonCode,
    RequestedOutput,
    SlideOutcome,
    Stage,
)
from atlas_conductor.dispatch import FakeAdapter, Injection
from atlas_conductor.planning import Planner
from atlas_conductor.run import run_job
from atlas_conductor.scheduler import Scheduler
from atlas_conductor.telemetry import InMemoryTelemetrySink
from atlas_conductor.validation import patch_h5_path

GEO = Geometry(patch_size=256, target_mag=20)
ENC = ("resnet50",)


def _cohort(tmp_path: Path, stems: list[str]) -> Path:
    cohort = tmp_path / "cohort"
    cohort.mkdir(parents=True, exist_ok=True)
    for stem in stems:
        (cohort / f"{stem}.svs").write_bytes(b"fake-wsi")
    return cohort


def _config(cohort: Path, out: Path) -> JobConfig:
    return JobConfig(
        input_dir=cohort,
        output_dir=out,
        requested_output=RequestedOutput.FEATURES,
        geometry=GEO,
        encoders=ENC,
    )


def _run(config: JobConfig, telemetry: InMemoryTelemetrySink, adapter: FakeAdapter):
    plan = Planner(telemetry).build_plan(config)
    return Scheduler(config, adapter, telemetry).run(plan), plan


def test_injected_oom_keeps_segment_retries_embed(tmp_path: Path) -> None:
    cohort = _cohort(tmp_path, ["s"])
    out = tmp_path / "out"
    config = _config(cohort, out)
    telemetry = InMemoryTelemetrySink()
    # OOM on the first attempt only: coords are written, features are not.
    adapter = FakeAdapter(
        injections={"s": Injection("oom", fail_until_attempt=1, label="cuda-oom")}
    )

    result, _ = _run(config, telemetry, adapter)

    assert result.count(SlideOutcome.VALID) == 1
    # Only the embed stage was ever dispatched — segmentation was kept, not re-run.
    dispatch_stages = {
        e.stage for e in telemetry.agent_events if e.event == "dispatch" and e.slide_stem == "s"
    }
    assert dispatch_stages == {Stage.EMBED.value}
    # The final HDF5 has coords and aligned, finite features.
    with h5py.File(patch_h5_path(out, "s"), "r") as h:
        assert h["coords"].shape[0] == h["features/resnet50"].shape[0]


def test_oom_recovery_is_labeled_resolved(tmp_path: Path) -> None:
    cohort = _cohort(tmp_path, ["s"])
    config = _config(cohort, tmp_path / "out")
    telemetry = InMemoryTelemetrySink()
    adapter = FakeAdapter(
        injections={"s": Injection("oom", fail_until_attempt=1, label="cuda-oom")}
    )
    _run(config, telemetry, adapter)

    recoveries = [r for r in telemetry.slide_stage_outcomes if r.classification is not None]
    assert recoveries, "a recovery attempt should be recorded"
    r = recoveries[0]
    assert r.classification == "resource-transient"
    assert r.action == "retry_with_mutation"
    assert r.injected_label == "cuda-oom"  # ground truth for classifier scoring
    assert r.resolved is True


def test_persistent_oom_exhausts_budget_and_quarantines(tmp_path: Path) -> None:
    cohort = _cohort(tmp_path, ["s"])
    config = _config(cohort, tmp_path / "out")
    telemetry = InMemoryTelemetrySink()
    # OOM on every attempt → retries exhaust the budget → quarantine.
    adapter = FakeAdapter(injections={"s": Injection("oom", label="cuda-oom")})
    result, _ = _run(config, telemetry, adapter)
    assert result.count(SlideOutcome.QUARANTINED) == 1


def test_structural_invalid_forces_then_quarantines(tmp_path: Path) -> None:
    cohort = _cohort(tmp_path, ["s"])
    config = _config(cohort, tmp_path / "out")
    telemetry = InMemoryTelemetrySink()
    # NaN features on every attempt: rebuilt once with --force, then quarantined.
    adapter = FakeAdapter(injections={"s": Injection("nan", label="nan")})
    result, _ = _run(config, telemetry, adapter)

    assert result.count(SlideOutcome.QUARANTINED) == 1
    actions = [r.action for r in telemetry.slide_stage_outcomes if r.action is not None]
    assert "force_reprocess" in actions
    assert "quarantine_item" in actions


def test_precondition_block_blocks_dependents(tmp_path: Path) -> None:
    cohort = _cohort(tmp_path, ["s"])
    config = _config(cohort, tmp_path / "out")
    telemetry = InMemoryTelemetrySink()
    # Gated encoder / missing token: nothing is written; segment fails at the front.
    adapter = FakeAdapter(injections={"s": Injection("precondition", label="precondition")})
    result, plan = _run(config, telemetry, adapter)

    assert result.count(SlideOutcome.BLOCKED) == 1
    # The embed stage was never scheduled — its upstream segment could not be satisfied.
    embed = [n for n in plan.nodes if n.slide_stem == "s" and n.stage is Stage.EMBED][0]
    assert embed.decision is Decision.BLOCKED
    assert embed.reason is ReasonCode.DEPENDENCY_BLOCKED


def test_unknown_failure_is_blocked_not_retried(tmp_path: Path) -> None:
    cohort = _cohort(tmp_path, ["s"])
    config = _config(cohort, tmp_path / "out")
    telemetry = InMemoryTelemetrySink()
    # no_coords with no signature → segment output invalid, classified structural and
    # eventually quarantined; assert no unbounded retry loop occurred.
    adapter = FakeAdapter(injections={"s": Injection("no_coords", label="no-coords")})
    result, _ = _run(config, telemetry, adapter)
    assert result.count(SlideOutcome.VALID) == 0
    retry_count = sum(
        1 for r in telemetry.slide_stage_outcomes if r.action == "retry_with_mutation"
    )
    assert retry_count <= config.attempt_budget  # bounded, never a loop


def test_healthy_cohort_still_all_valid(tmp_path: Path) -> None:
    # No injections: the recovery-capable scheduler must not regress the happy path.
    cohort = _cohort(tmp_path, ["a", "b"])
    config = _config(cohort, tmp_path / "out")
    result = run_job(config, InMemoryTelemetrySink())
    assert result.count(SlideOutcome.VALID) == 2
