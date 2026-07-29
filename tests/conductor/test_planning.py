"""Tests for planner reconciliation and geometry-conflict blocking (task 9.2).

Exercises the state × requested-output decision table (skip / run / reuse / blocked)
and the plan-time geometry-conflict block, driving the planner against real
pre-existing HDF5 outputs on disk.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import Decision, Geometry, ReasonCode, RequestedOutput, Stage
from atlas_conductor.planning import Planner
from atlas_conductor.telemetry import InMemoryTelemetrySink
from atlas_conductor.validation import patch_h5_path
from tests.conductor.h5_fixtures import write_patch_h5

GEO = Geometry(patch_size=256, target_mag=20)
ENC = ("resnet50",)


def _cohort(tmp_path: Path, stems: list[str]) -> Path:
    cohort = tmp_path / "cohort"
    cohort.mkdir(parents=True, exist_ok=True)
    for stem in stems:
        (cohort / f"{stem}.svs").write_bytes(b"fake-wsi")
    return cohort


def _config(cohort: Path, out: Path, output: RequestedOutput) -> JobConfig:
    return JobConfig(
        input_dir=cohort,
        output_dir=out,
        requested_output=output,
        geometry=GEO,
        encoders=ENC if output is RequestedOutput.FEATURES else (),
    )


def _terminal_decision(plan, stem: str, stage: Stage) -> Decision:
    (node,) = (n for n in plan.nodes if n.slide_stem == stem and n.stage == stage)
    return node.decision


def test_no_output_runs(tmp_path: Path) -> None:
    cohort = _cohort(tmp_path, ["s"])
    plan = Planner(InMemoryTelemetrySink()).build_plan(
        _config(cohort, tmp_path / "out", RequestedOutput.FEATURES)
    )
    assert _terminal_decision(plan, "s", Stage.SEGMENT) is Decision.RUN
    assert _terminal_decision(plan, "s", Stage.EMBED) is Decision.RUN


def test_valid_features_skipped(tmp_path: Path) -> None:
    cohort = _cohort(tmp_path, ["s"])
    out = tmp_path / "out"
    write_patch_h5(patch_h5_path(out, "s"), encoders=ENC)
    plan = Planner(InMemoryTelemetrySink()).build_plan(
        _config(cohort, out, RequestedOutput.FEATURES)
    )
    assert _terminal_decision(plan, "s", Stage.EMBED) is Decision.SKIP


def test_coords_valid_features_requested_reuses(tmp_path: Path) -> None:
    cohort = _cohort(tmp_path, ["s"])
    out = tmp_path / "out"
    write_patch_h5(patch_h5_path(out, "s"))  # coords only, no features
    plan = Planner(InMemoryTelemetrySink()).build_plan(
        _config(cohort, out, RequestedOutput.FEATURES)
    )
    assert _terminal_decision(plan, "s", Stage.SEGMENT) is Decision.SKIP
    assert _terminal_decision(plan, "s", Stage.EMBED) is Decision.REUSE


def test_coords_valid_coords_requested_skips(tmp_path: Path) -> None:
    cohort = _cohort(tmp_path, ["s"])
    out = tmp_path / "out"
    write_patch_h5(patch_h5_path(out, "s"))
    plan = Planner(InMemoryTelemetrySink()).build_plan(_config(cohort, out, RequestedOutput.COORDS))
    assert _terminal_decision(plan, "s", Stage.SEGMENT) is Decision.SKIP


def test_branch_on_output_same_slide(tmp_path: Path) -> None:
    # Coords-only output: coords job skips, features job runs (reuse) — same file.
    cohort = _cohort(tmp_path, ["s"])
    out = tmp_path / "out"
    write_patch_h5(patch_h5_path(out, "s"))
    coords_plan = Planner(InMemoryTelemetrySink()).build_plan(
        _config(cohort, out, RequestedOutput.COORDS)
    )
    features_plan = Planner(InMemoryTelemetrySink()).build_plan(
        _config(cohort, out, RequestedOutput.FEATURES)
    )
    assert _terminal_decision(coords_plan, "s", Stage.SEGMENT) is Decision.SKIP
    assert _terminal_decision(features_plan, "s", Stage.EMBED) is Decision.REUSE


def test_geometry_conflict_blocks(tmp_path: Path) -> None:
    cohort = _cohort(tmp_path, ["s"])
    out = tmp_path / "out"
    # Existing HDF5 at patch_size=512; job requests 256 → geometry conflict.
    write_patch_h5(patch_h5_path(out, "s"), patch_size=512)
    telemetry = InMemoryTelemetrySink()
    plan = Planner(telemetry).build_plan(_config(cohort, out, RequestedOutput.COORDS))
    (node,) = (n for n in plan.nodes if n.slide_stem == "s")
    assert node.decision is Decision.BLOCKED
    assert node.reason is ReasonCode.GEOMETRY_MISMATCH
    assert "--force" in node.detail  # actionable message


@pytest.mark.parametrize("output", [RequestedOutput.COORDS, RequestedOutput.FEATURES])
def test_geometry_conflict_blocks_both_outputs(tmp_path: Path, output: RequestedOutput) -> None:
    cohort = _cohort(tmp_path, ["s"])
    out = tmp_path / "out"
    write_patch_h5(patch_h5_path(out, "s"), patch_size=512, encoders=ENC)
    plan = Planner(InMemoryTelemetrySink()).build_plan(_config(cohort, out, output))
    assert all(n.decision is Decision.BLOCKED for n in plan.nodes if n.slide_stem == "s")
