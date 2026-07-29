"""Tests for the plan-time input-admissibility gate (task 9.7, design D16).

Each inadmissible case blocks before dispatch with the right reason code, and the check
is shallow — it never decodes a slide.
"""

from __future__ import annotations

from pathlib import Path

from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import Decision, Geometry, ReasonCode, RequestedOutput, SlideOutcome
from atlas_conductor.planning import Planner, check_admissibility
from atlas_conductor.run import run_job
from atlas_conductor.telemetry import InMemoryTelemetrySink

GEO = Geometry(patch_size=256, target_mag=20)


def _config(cohort: Path, out: Path) -> JobConfig:
    return JobConfig(
        input_dir=cohort,
        output_dir=out,
        requested_output=RequestedOutput.COORDS,
        geometry=GEO,
    )


def test_empty_cohort_blocks(tmp_path: Path) -> None:
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    admit = check_admissibility(cohort)
    assert admit.cohort_block is ReasonCode.EMPTY_COHORT

    plan = Planner(InMemoryTelemetrySink()).build_plan(_config(cohort, tmp_path / "out"))
    assert plan.is_blocked
    assert plan.blocked_reason is ReasonCode.EMPTY_COHORT
    assert plan.nodes == []


def test_missing_cohort_dir_blocks_empty(tmp_path: Path) -> None:
    admit = check_admissibility(tmp_path / "does-not-exist")
    assert admit.cohort_block is ReasonCode.EMPTY_COHORT


def test_no_wsi_files_blocks(tmp_path: Path) -> None:
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    (cohort / "readme.txt").write_text("not a slide")
    (cohort / "notes.md").write_text("nor this")
    admit = check_admissibility(cohort)
    assert admit.cohort_block is ReasonCode.NO_WSI_FILES

    plan = Planner(InMemoryTelemetrySink()).build_plan(_config(cohort, tmp_path / "out"))
    assert plan.blocked_reason is ReasonCode.NO_WSI_FILES


def test_zero_byte_wsi_is_unreadable_input(tmp_path: Path) -> None:
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    (cohort / "good.svs").write_bytes(b"data")
    (cohort / "empty.svs").write_bytes(b"")  # zero bytes → inadmissible
    admit = check_admissibility(cohort)
    assert admit.cohort_block is None
    assert [p.name for p in admit.admissible] == ["good.svs"]
    assert admit.inadmissible[0][1] is ReasonCode.UNREADABLE_INPUT

    plan = Planner(InMemoryTelemetrySink()).build_plan(_config(cohort, tmp_path / "out"))
    blocked = [n for n in plan.nodes if n.slide_stem == "empty"]
    assert blocked and all(n.decision is Decision.BLOCKED for n in blocked)
    assert blocked[0].reason is ReasonCode.UNREADABLE_INPUT


def test_run_reports_blocked_cohort_without_dispatch(tmp_path: Path) -> None:
    cohort = tmp_path / "cohort"
    cohort.mkdir()  # empty
    out = tmp_path / "out"
    result = run_job(_config(cohort, out), InMemoryTelemetrySink())
    assert result.count(SlideOutcome.BLOCKED) == result.cohort_size
    # Nothing was written — no dispatch happened.
    assert not (out / "patches").exists()


def test_admissibility_does_not_decode_slides(tmp_path: Path) -> None:
    # A file with a WSI extension but garbage contents is admissible (shallow check);
    # deep decode is AtlasPatch's job, not the gate's.
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    (cohort / "garbage.svs").write_bytes(b"definitely not a valid slide")
    admit = check_admissibility(cohort)
    assert admit.cohort_block is None
    assert [p.name for p in admit.admissible] == ["garbage.svs"]
    assert admit.inadmissible == []
