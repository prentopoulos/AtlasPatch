"""Tests for --dry-run and the decision trace (tasks 4.5, 8.3, 9.8).

The dry run reconciles and reports per-slide decisions without dispatching; the report
and dry run surface the ordered per-slide decisions sourced from the typed telemetry
records, carrying operational metadata only.
"""

from __future__ import annotations

from pathlib import Path

from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import Geometry, RequestedOutput
from atlas_conductor.report import build_dry_run_report, build_report
from atlas_conductor.run import plan_job, run_job
from atlas_conductor.telemetry import InMemoryTelemetrySink
from atlas_conductor.trace import slide_traces
from atlas_conductor.validation import patch_h5_path
from tests.conductor.h5_fixtures import write_patch_h5

GEO = Geometry(patch_size=256, target_mag=20)
ENC = ("resnet50",)


def _mixed_cohort(tmp_path: Path) -> tuple[JobConfig, Path]:
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    for stem in ["fresh", "done", "conflict"]:
        (cohort / f"{stem}.svs").write_bytes(b"fake-wsi")
    out = tmp_path / "out"
    write_patch_h5(patch_h5_path(out, "done"), encoders=ENC)  # already valid → skip
    write_patch_h5(patch_h5_path(out, "conflict"), patch_size=512, encoders=ENC)  # blocked
    config = JobConfig(
        input_dir=cohort,
        output_dir=out,
        requested_output=RequestedOutput.FEATURES,
        geometry=GEO,
        encoders=ENC,
    )
    return config, out


def test_dry_run_shows_decisions(tmp_path: Path) -> None:
    config, _ = _mixed_cohort(tmp_path)
    telemetry = InMemoryTelemetrySink()
    plan = plan_job(config, telemetry)
    report = build_dry_run_report(plan, telemetry)

    assert "DRY RUN" in report
    assert "no work dispatched" in report
    # Each slide's decision is visible.
    lines = {line.split()[0]: line for line in report.splitlines() if line.startswith("  ")}
    assert "run" in lines["fresh"]
    assert "skip" in lines["done"]
    assert "blocked" in lines["conflict"]


def test_dry_run_dispatches_nothing(tmp_path: Path) -> None:
    config, out = _mixed_cohort(tmp_path)
    plan_job(config, InMemoryTelemetrySink())
    # The fresh slide would run, but a dry run must write no output for it.
    assert not patch_h5_path(out, "fresh").exists()


def test_trace_surfaces_ordered_decisions(tmp_path: Path) -> None:
    config, _ = _mixed_cohort(tmp_path)
    telemetry = InMemoryTelemetrySink()
    run_job(config, telemetry)
    traces = slide_traces(telemetry)

    # A slide that ran shows reconcile → dispatch → verdict, in order.
    fresh_steps = [e["event"] for e in traces["fresh"]]
    assert fresh_steps == ["reconcile", "dispatch", "verdict"]
    # A skipped slide was never dispatched.
    done_steps = [e["event"] for e in traces["done"]]
    assert "dispatch" not in done_steps


def test_trace_is_operational_metadata_only(tmp_path: Path) -> None:
    config, _ = _mixed_cohort(tmp_path)
    telemetry = InMemoryTelemetrySink()
    run_job(config, telemetry)
    traces = slide_traces(telemetry)

    operational_keys = {
        "job_id",
        "agent",
        "event",
        "slide_stem",
        "stage",
        "reason_code",
        "detail",
        "timestamp",
    }
    for events in traces.values():
        for event in events:
            assert set(event) <= operational_keys  # no pixel/array field can appear


def test_report_trace_detail_on_demand(tmp_path: Path) -> None:
    config, _ = _mixed_cohort(tmp_path)
    telemetry = InMemoryTelemetrySink()
    result = run_job(config, telemetry)

    # Summary-first: with trace='none' the per-slide steps are suppressed.
    summary_only = build_report(result, telemetry, trace="none")
    assert "reconcile" not in summary_only
    # Failures/blocked show their trace by default.
    with_failures = build_report(result, telemetry, trace="failures")
    assert "planner:blocked" in with_failures or "blocked" in with_failures
