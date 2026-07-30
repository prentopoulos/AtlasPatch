"""Tests for the frozen observability snapshot (gui-snapshot spec, tasks 3.1-3.5, 3.7).

The snapshot is the single versioned machine-readable payload every observability renderer
consumes. These tests pin its contract: a sink→JSONL→reader→snapshot round-trip reproduces the
recorded run state (verdicts, reason codes, cohort counts, trace, derived state); the payload
carries no clinical score and no pixel/embedding and no raw identifier; derived choreography and
message-flow state degrade cleanly; empty telemetry assembles to a well-formed versioned payload;
and importing the module pulls in no ``streamlit`` and no ``atlas_patch`` (design D-SNAP-4/5).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import Geometry, RequestedOutput
from atlas_conductor.gui.reader import TelemetryReader
from atlas_conductor.gui.snapshot import (
    SNAPSHOT_SCHEMA_VERSION,
    assemble_snapshot,
    run_snapshot,
)
from atlas_conductor.run import run_job
from atlas_conductor.telemetry import (
    AgentEventRecord,
    JobRecord,
    JsonlTelemetrySink,
    MessageFlowRecord,
    SlideStageOutcomeRecord,
    ValidationResultRecord,
)

GEO = Geometry(patch_size=256, target_mag=20)


def _write_run(directory: Path) -> None:
    """Write one two-slide run (one valid, one quarantined) with events and message flow."""
    sink = JsonlTelemetrySink(directory)
    sink.record_job(
        JobRecord(
            job_id="j1",
            input_dir="cohort",
            requested_output="coords",
            patch_size=256,
            target_mag=20,
            encoders="",
            adapter="fake",
            status="completed",
            cohort_size=2,
            valid_count=1,
            quarantined_count=1,
        )
    )
    sink.record_slide_stage_outcome(
        SlideStageOutcomeRecord(
            job_id="j1",
            slide_stem="p-aaa",
            stage="segment",
            command="segment-and-get-coords",
            attempt=1,
            outcome="valid",
            reason_code="valid",
        )
    )
    sink.record_slide_stage_outcome(
        SlideStageOutcomeRecord(
            job_id="j1",
            slide_stem="p-bbb",
            stage="segment",
            command="segment-and-get-coords",
            attempt=1,
            outcome="quarantined",
            reason_code="empty_h5",
        )
    )
    sink.record_validation(
        ValidationResultRecord(
            job_id="j1",
            slide_stem="p-aaa",
            stage="segment",
            requested_output="coords",
            valid=True,
            reason_code="valid",
            detail="12 patches",
        )
    )
    sink.record_validation(
        ValidationResultRecord(
            job_id="j1",
            slide_stem="p-bbb",
            stage="segment",
            requested_output="coords",
            valid=False,
            reason_code="empty_h5",
            detail="0 patches",
        )
    )
    # Ordered agent events; the last one (validator on p-bbb) drives the choreography ticker.
    sink.record_agent_event(
        AgentEventRecord(
            job_id="j1", agent="planner", event="planned", timestamp="2026-07-30T00:00:01"
        )
    )
    sink.record_agent_event(
        AgentEventRecord(
            job_id="j1",
            agent="validator",
            event="verdict",
            slide_stem="p-aaa",
            stage="segment",
            reason_code="valid",
            timestamp="2026-07-30T00:00:02",
        )
    )
    sink.record_agent_event(
        AgentEventRecord(
            job_id="j1",
            agent="validator",
            event="verdict",
            slide_stem="p-bbb",
            stage="segment",
            reason_code="empty_h5",
            timestamp="2026-07-30T00:00:03",
        )
    )
    sink.record_message_flow(
        MessageFlowRecord(
            job_id="j1",
            from_agent="planner",
            to_agent="worker",
            message_type="dispatch",
            correlation_id="c1",
            timestamp="2026-07-30T00:00:01",
        )
    )
    sink.record_message_flow(
        MessageFlowRecord(
            job_id="j1",
            from_agent="worker",
            to_agent="validator",
            message_type="verify",
            correlation_id="c2",
            timestamp="2026-07-30T00:00:02",
        )
    )


def test_round_trip_preserves_run_state(tmp_path: Path) -> None:
    _write_run(tmp_path)
    snap = assemble_snapshot(TelemetryReader(tmp_path))

    assert snap["schema_version"] == SNAPSHOT_SCHEMA_VERSION
    assert len(snap["runs"]) == 1
    run = snap["runs"][0]

    # Cohort metrics tally the terminal outcomes and match the per-slide verdicts.
    assert run["cohort_size"] == 2
    assert run["counts"] == {"valid": 1, "skipped": 0, "quarantined": 1, "blocked": 0}
    slides = {s["slide_stem"]: s for s in run["slides"]}
    assert slides["p-aaa"]["outcome"] == "valid"
    assert slides["p-aaa"]["reason_code"] == "valid"
    assert slides["p-aaa"]["detail"] == "12 patches"
    assert slides["p-bbb"]["outcome"] == "quarantined"
    assert slides["p-bbb"]["reason_code"] == "empty_h5"
    # The decision trace is present per slide (grouped agent_events).
    assert slides["p-aaa"]["trace"] and slides["p-bbb"]["trace"]

    # Derived Level-1 choreography: the latest event's actor is active, others idle.
    choreo = run["choreography"]
    assert choreo["active"] == "validator"
    assert choreo["lit"]["validator"] is True
    assert choreo["lit"]["planner"] is False
    assert choreo["now_processing"] == "slide p-bbb · stage segment"

    # Derived Level-2 message flow: both directed edges present, latest is worker→validator.
    flow = run["message_flow"]
    assert flow["has_flow"] is True
    edge_pairs = {(e["from_agent"], e["to_agent"]) for e in flow["edges"]}
    assert edge_pairs == {("planner", "worker"), ("worker", "validator")}
    assert flow["latest"] == ["worker", "validator"]


def test_snapshot_carries_no_score_or_pixel(tmp_path: Path) -> None:
    _write_run(tmp_path)
    blob = json.dumps(assemble_snapshot(tmp_path)).lower()
    # No clinical score tokens anywhere in the serialized payload (D-SNAP-4).
    for token in ("confidence", "probability", "score", "logit", "softmax"):
        assert token not in blob
    # No pixel / mask / heatmap / embedding data (structural verdicts only).
    for token in ("pixel", "heatmap", "embedding", '"mask"', "grad_cam", "gradcam"):
        assert token not in blob


def test_snapshot_is_phi_free(tmp_path: Path) -> None:
    # A numeric stem is itself an identifier; run_job pseudonymizes it, so the assembled
    # snapshot must show only the pseudonym and never the raw identifier (D-SNAP-4).
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    (cohort / "987654321.svs").write_bytes(b"fake-wsi")
    tele = tmp_path / "tele"
    run_job(
        JobConfig(
            input_dir=cohort,
            output_dir=tmp_path / "out",
            requested_output=RequestedOutput.FEATURES,
            geometry=GEO,
            encoders=("resnet50",),
        ),
        JsonlTelemetrySink(tele),
    )
    blob = json.dumps(assemble_snapshot(tele))
    assert "987654321" not in blob
    assert len(json.loads(blob)["runs"]) == 1


def test_derived_state_degrades_cleanly(tmp_path: Path) -> None:
    # A run with no agent_events and no message_flow: idle choreography, no fabricated edges.
    sink = JsonlTelemetrySink(tmp_path)
    sink.record_job(
        JobRecord(
            job_id="bare",
            input_dir="cohort",
            requested_output="coords",
            patch_size=256,
            target_mag=20,
            encoders="",
            adapter="fake",
            status="completed",
            cohort_size=1,
            valid_count=1,
        )
    )
    sink.record_slide_stage_outcome(
        SlideStageOutcomeRecord(
            job_id="bare",
            slide_stem="p-solo",
            stage="segment",
            command="segment-and-get-coords",
            attempt=1,
            outcome="valid",
            reason_code="valid",
        )
    )
    run = assemble_snapshot(tmp_path)["runs"][0]
    choreo = run["choreography"]
    assert choreo["active"] is None
    assert choreo["now_processing"] is None
    assert all(lit is False for lit in choreo["lit"].values())
    flow = run["message_flow"]
    assert flow["has_flow"] is False
    assert flow["edges"] == []
    assert flow["latest"] is None


def test_empty_telemetry_assembles_versioned_payload(tmp_path: Path) -> None:
    snap = assemble_snapshot(tmp_path / "never-written")
    # Well-formed versioned payload with an empty runs set, no exception (gui-snapshot: empty).
    assert snap["schema_version"] == SNAPSHOT_SCHEMA_VERSION
    assert snap["runs"] == []


def test_top_level_shape_is_pinned(tmp_path: Path) -> None:
    # A shape test on the top-level keys makes an unversioned breaking change fail CI (D-SNAP-2).
    _write_run(tmp_path)
    snap = assemble_snapshot(tmp_path)
    assert set(snap.keys()) == {"schema_version", "agents", "runs"}
    assert snap["agents"] == ["planner", "worker", "validator", "recovery", "scheduler"]
    run = snap["runs"][0]
    assert set(run.keys()) == {
        "job_id",
        "job",
        "cohort_size",
        "counts",
        "slides",
        "choreography",
        "message_flow",
    }


def test_run_snapshot_matches_assembled_run(tmp_path: Path) -> None:
    # assemble_snapshot serializes each view via run_snapshot — the two must agree.
    from atlas_conductor.gui.model import build_run_views

    _write_run(tmp_path)
    views = build_run_views(TelemetryReader(tmp_path))
    assert assemble_snapshot(tmp_path)["runs"] == [run_snapshot(v) for v in views]


def test_importing_snapshot_pulls_no_streamlit_or_atlas_patch() -> None:
    # The contract must be consumable without the GUI runtime or the ML package (D-SNAP-5).
    forbidden = ["streamlit", "atlas_patch"]
    code = (
        "import atlas_conductor.gui.snapshot, sys; "
        f"leaked = [m for m in {forbidden!r} if m in sys.modules]; "
        "assert not leaked, f'forbidden import leaked into the snapshot module: {leaked}'"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
