"""Tests for the read-only telemetry reader (task 1.3, observability-gui spec).

The reader round-trips what ``JsonlTelemetrySink`` writes, reads a clean empty state when
the sink has not been written to, and exposes no write path.
"""

from __future__ import annotations

from pathlib import Path

from atlas_conductor.gui.reader import FAMILIES, TelemetryReader
from atlas_conductor.telemetry import (
    AgentEventRecord,
    JobRecord,
    JsonlTelemetrySink,
    SlideStageOutcomeRecord,
    ValidationResultRecord,
)


def _write_one_of_each(directory: Path) -> JsonlTelemetrySink:
    sink = JsonlTelemetrySink(directory)
    sink.record_job(
        JobRecord(
            job_id="j",
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
            job_id="j",
            slide_stem="p-abc",
            stage="segment",
            command="segment-and-get-coords",
            attempt=1,
            outcome="valid",
            reason_code="valid",
        )
    )
    sink.record_validation(
        ValidationResultRecord(
            job_id="j",
            slide_stem="p-abc",
            stage="segment",
            requested_output="coords",
            valid=True,
            reason_code="valid",
        )
    )
    sink.record_agent_event(
        AgentEventRecord(job_id="j", agent="validator", event="verdict", slide_stem="p-abc")
    )
    return sink


def test_reader_round_trips_every_family(tmp_path: Path) -> None:
    _write_one_of_each(tmp_path)
    reader = TelemetryReader(tmp_path)

    assert len(reader.jobs()) == 1
    assert reader.jobs()[0]["job_id"] == "j"
    assert reader.slide_stage_outcomes()[0]["outcome"] == "valid"
    assert reader.validation_results()[0]["valid"] is True
    assert reader.agent_events()[0]["event"] == "verdict"
    assert not reader.is_empty()


def test_reader_reads_empty_state_for_absent_sink(tmp_path: Path) -> None:
    reader = TelemetryReader(tmp_path / "never-written")
    for family in FAMILIES:
        assert getattr(reader, family)() == []
    assert reader.is_empty()


def test_reader_exposes_no_write_method() -> None:
    # The read surface must not be able to mutate telemetry (design D-GUI-1).
    reader_attrs = set(dir(TelemetryReader))
    assert not reader_attrs & {"record_job", "record_agent_event", "append", "write", "_append"}
