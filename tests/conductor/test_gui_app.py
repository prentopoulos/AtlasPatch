"""AppTest suite for the observability GUI (tasks 6.1-6.3, observability-gui spec).

Uses Streamlit's headless harness — no browser, server, or GPU — to assert the panels
populate from PHI-free telemetry and the D18 guardrails hold: no image element is ever
rendered, verdicts carry no confidence score, and gated runs render pseudonyms not raw
identifiers.
"""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import Geometry, RequestedOutput
from atlas_conductor.run import run_job
from atlas_conductor.telemetry import (
    AgentEventRecord,
    JobRecord,
    JsonlTelemetrySink,
    SlideStageOutcomeRecord,
    ValidationResultRecord,
)

APP = str(Path("atlas_conductor/gui/app.py"))
GEO = Geometry(patch_size=256, target_mag=20)


def _apptest(telemetry_dir: Path) -> AppTest:
    at = AppTest.from_file(APP)
    at.session_state["telemetry_dir"] = str(telemetry_dir)
    at.run()
    return at


def _run_cohort(tmp_path: Path, stems: list[str]) -> Path:
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    for stem in stems:
        (cohort / f"{stem}.svs").write_bytes(b"fake-wsi")
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
    return tele


def _write_controlled(tele: Path) -> None:
    # A run whose latest agent event is the validator on slideB/segment.
    sink = JsonlTelemetrySink(tele)
    sink.record_job(
        JobRecord(
            job_id="j",
            input_dir="cohort",
            requested_output="coords",
            patch_size=256,
            target_mag=20,
            encoders="",
            adapter="fake",
            status="complete",
            cohort_size=2,
            valid_count=1,
            quarantined_count=1,
        )
    )
    for stem, outcome in (("slideA", "valid"), ("slideB", "quarantined")):
        sink.record_slide_stage_outcome(
            SlideStageOutcomeRecord(
                job_id="j",
                slide_stem=stem,
                stage="segment",
                command="segment-and-get-coords",
                attempt=1,
                outcome=outcome,
                reason_code="valid" if outcome == "valid" else "corrupt",
            )
        )
        sink.record_validation(
            ValidationResultRecord(
                job_id="j",
                slide_stem=stem,
                stage="segment",
                requested_output="coords",
                valid=outcome == "valid",
                reason_code="valid" if outcome == "valid" else "corrupt",
            )
        )
    sink.record_agent_event(
        AgentEventRecord(
            job_id="j", agent="worker", event="dispatch", slide_stem="slideA", stage="segment"
        )
    )
    sink.record_agent_event(
        AgentEventRecord(
            job_id="j", agent="validator", event="verdict", slide_stem="slideB", stage="segment"
        )
    )


# -- empty state -----------------------------------------------------------------


def test_empty_state_renders_without_error(tmp_path: Path) -> None:
    at = _apptest(tmp_path / "never")
    assert not at.exception
    assert any("No runs recorded" in info.value for info in at.info)


# -- panels populate (6.1) -------------------------------------------------------


def test_panels_populate_from_telemetry(tmp_path: Path) -> None:
    at = _apptest(_run_cohort(tmp_path, ["a", "b", "c"]))
    assert not at.exception
    assert at.title  # the app rendered
    # history + verdict dataframes both present.
    assert len(at.dataframe) >= 2
    # cohort + four terminal outcomes.
    labels = {m.label for m in at.metric}
    assert {"cohort", "valid", "skipped", "quarantined", "blocked"} <= labels
    cohort_metric = next(m for m in at.metric if m.label == "cohort")
    assert cohort_metric.value == "3"


# -- guardrails (6.2) ------------------------------------------------------------


def test_no_image_element_is_ever_rendered(tmp_path: Path) -> None:
    at = _apptest(_run_cohort(tmp_path, ["a", "b"]))
    assert at.get("imgs") == []  # no slide pixel, mask, or heatmap ever


def test_verdicts_carry_no_confidence_score(tmp_path: Path) -> None:
    at = _apptest(_run_cohort(tmp_path, ["a", "b"]))
    blob = " ".join(m.value for m in at.markdown).lower()
    blob += " ".join(str(m.label) for m in at.metric).lower()
    for forbidden in ("confidence", "probability", "score", "grad-cam", "saliency"):
        assert forbidden not in blob


def test_gated_run_renders_pseudonym_not_raw_identifier(tmp_path: Path) -> None:
    # A stem that is itself an identifier: the GUI must show only its pseudonym.
    at = _apptest(_run_cohort(tmp_path, ["987654321"]))
    rendered = " ".join(m.value for m in at.markdown)
    assert "987654321" not in rendered


# -- choreography in the app (6.3) -----------------------------------------------


def test_choreography_marks_latest_actor_active_with_ticker(tmp_path: Path) -> None:
    tele = tmp_path / "tele"
    _write_controlled(tele)
    at = _apptest(tele)
    assert not at.exception
    blob = "\n".join(m.value for m in at.markdown)
    # The validator (latest actor) is active; the ticker names its slide and stage.
    assert "**validator** — 🟢 active" in blob
    assert "**planner** — ⚪ idle" in blob
    assert "Now processing: slide slideB · stage segment" in blob
