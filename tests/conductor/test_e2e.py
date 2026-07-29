"""End-to-end no-GPU walking-skeleton test (task 9.1 — happy-path assertion).

Runs the full slice-A1 loop — plan → dispatch → validate → report → telemetry —
against the fake adapter with no GPU and no real slides, and asserts the cohort comes
out valid and reconstructable from telemetry. The stage-granular recovery assertion
(segment kept, only embed retried on injected OOM) is added in slice A3.
"""

from __future__ import annotations

from pathlib import Path

from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import Geometry, RequestedOutput, SlideOutcome
from atlas_conductor.report import build_report
from atlas_conductor.run import run_job
from atlas_conductor.telemetry import InMemoryTelemetrySink, JsonlTelemetrySink
from atlas_conductor.validation import patch_h5_path, validate_output


def _make_cohort(root: Path, stems: list[str]) -> Path:
    cohort = root / "cohort"
    cohort.mkdir(parents=True, exist_ok=True)
    for stem in stems:
        (cohort / f"{stem}.svs").write_bytes(b"fake-wsi")
    return cohort


def _features_config(cohort: Path, out: Path) -> JobConfig:
    return JobConfig(
        input_dir=cohort,
        output_dir=out,
        requested_output=RequestedOutput.FEATURES,
        geometry=Geometry(patch_size=256, target_mag=20),
        encoders=("resnet50",),
    )


def test_happy_path_all_valid(tmp_path: Path) -> None:
    cohort = _make_cohort(tmp_path, ["slide_a", "slide_b", "slide_c"])
    out = tmp_path / "out"
    config = _features_config(cohort, out)
    telemetry = InMemoryTelemetrySink()

    result = run_job(config, telemetry)

    assert result.cohort_size == 3
    assert result.count(SlideOutcome.VALID) == 3
    assert all(s.outcome is SlideOutcome.VALID for s in result.slides)

    # Each slide's HDF5 was actually written and independently validates.
    for stem in ["slide_a", "slide_b", "slide_c"]:
        h5 = patch_h5_path(out, stem)
        assert h5.exists()
        assert validate_output(h5, config.geometry, RequestedOutput.FEATURES, config.encoders).valid


def test_report_reflects_verdicts(tmp_path: Path) -> None:
    cohort = _make_cohort(tmp_path, ["slide_a"])
    config = _features_config(cohort, tmp_path / "out")
    result = run_job(config, InMemoryTelemetrySink())
    report = build_report(result)
    assert "slide_a" in report
    assert "valid=1" in report
    assert "cohort=1" in report


def test_second_run_skips_valid_work(tmp_path: Path) -> None:
    cohort = _make_cohort(tmp_path, ["slide_a", "slide_b"])
    config = _features_config(cohort, tmp_path / "out")

    run_job(config, InMemoryTelemetrySink())
    second = run_job(config, InMemoryTelemetrySink())

    # Everything is already valid on disk → all skipped, nothing re-run.
    assert second.count(SlideOutcome.SKIPPED) == 2
    assert second.count(SlideOutcome.VALID) == 0


def test_coords_job_reuse_then_features(tmp_path: Path) -> None:
    cohort = _make_cohort(tmp_path, ["slide_a"])
    out = tmp_path / "out"
    coords_cfg = JobConfig(
        input_dir=cohort,
        output_dir=out,
        requested_output=RequestedOutput.COORDS,
        geometry=Geometry(patch_size=256, target_mag=20),
    )
    coords_result = run_job(coords_cfg, InMemoryTelemetrySink())
    assert coords_result.count(SlideOutcome.VALID) == 1

    # Now request features on the same slide: coords already valid, features missing →
    # the slide still runs (reuse), and comes out valid.
    features_cfg = _features_config(cohort, out)
    features_result = run_job(features_cfg, InMemoryTelemetrySink())
    assert features_result.count(SlideOutcome.VALID) == 1


def test_telemetry_families_written_to_disk(tmp_path: Path) -> None:
    cohort = _make_cohort(tmp_path, ["slide_a", "slide_b"])
    config = _features_config(cohort, tmp_path / "out")
    sink = JsonlTelemetrySink(tmp_path / "telemetry")

    run_job(config, sink)

    jobs = sink.read_family("jobs")
    outcomes = sink.read_family("slide_stage_outcomes")
    validations = sink.read_family("validation_results")
    events = sink.read_family("agent_events")

    assert len(jobs) == 1
    assert jobs[0]["cohort_size"] == 2
    # Run is reconstructable, but stems are pseudonymized at rest (design D12): the raw
    # names never land, yet each slide's records stay correlatable within the run.
    from atlas_conductor.governance.phi import pseudonymize_stem

    job_id = jobs[0]["job_id"]
    expected = {pseudonymize_stem("slide_a", job_id), pseudonymize_stem("slide_b", job_id)}
    persisted = {r["slide_stem"] for r in outcomes}
    assert persisted == expected
    assert persisted.isdisjoint({"slide_a", "slide_b"})  # raw stem never persisted
    assert validations
    assert any(e["agent"] == "planner" for e in events)
    assert any(e["agent"] == "worker" for e in events)
    assert any(e["agent"] == "validator" for e in events)
