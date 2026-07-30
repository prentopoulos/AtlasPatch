"""Tests for the HTML/JSON report sibling (task 2.3, report-export spec).

The JSON sibling mirrors the terminal report's per-slide outcomes and cohort counts, the
export carries only PHI-free metadata (pseudonyms, never a raw identifier or pixel), and
the HTML sibling renders no image element.
"""

from __future__ import annotations

import json
from pathlib import Path

from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import Geometry, RequestedOutput, SlideOutcome
from atlas_conductor.gui.export import export_report
from atlas_conductor.gui.snapshot import SNAPSHOT_SCHEMA_VERSION
from atlas_conductor.run import run_job
from atlas_conductor.scheduler import RunResult
from atlas_conductor.telemetry import JsonlTelemetrySink

GEO = Geometry(patch_size=256, target_mag=20)


def _run_cohort(tmp_path: Path, stems: list[str]) -> tuple[Path, RunResult]:
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    for stem in stems:
        (cohort / f"{stem}.svs").write_bytes(b"fake-wsi")
    tele = tmp_path / "tele"
    config = JobConfig(
        input_dir=cohort,
        output_dir=tmp_path / "out",
        requested_output=RequestedOutput.FEATURES,
        geometry=GEO,
        encoders=("resnet50",),
    )
    result = run_job(config, JsonlTelemetrySink(tele))
    return tele, result


def test_json_sibling_mirrors_terminal_report_counts(tmp_path: Path) -> None:
    tele, result = _run_cohort(tmp_path, ["a", "b", "c"])
    doc = json.loads(export_report(tele, fmt="json"))

    assert len(doc["runs"]) == 1
    run = doc["runs"][0]
    # Cohort counts match the report's RunResult tallies.
    for outcome in SlideOutcome:
        assert run["counts"][outcome.value] == result.count(outcome)
    assert run["cohort_size"] == result.cohort_size
    # Every slide carries a structural verdict and reason code — and no confidence score.
    for slide in run["slides"]:
        assert slide["outcome"] in {o.value for o in SlideOutcome}
        assert "confidence" not in slide and "score" not in slide and "probability" not in slide


def test_export_carries_no_raw_identifier(tmp_path: Path) -> None:
    # A cohort whose stem is itself an identifier: the export must show the pseudonym only.
    tele, _ = _run_cohort(tmp_path, ["987654321"])
    for fmt in ("json", "html"):
        rendered = export_report(tele, fmt=fmt)
        assert "987654321" not in rendered  # raw identifier provably absent


def test_html_sibling_renders_no_image(tmp_path: Path) -> None:
    tele, _ = _run_cohort(tmp_path, ["a", "b"])
    doc = export_report(tele, fmt="html")
    assert "<img" not in doc.lower()
    assert "verdict" in doc.lower()  # it is a verdict report, not a prediction


def test_html_and_json_siblings_agree_on_a_run(tmp_path: Path) -> None:
    # The two siblings are assembled from the same read path; they must report identical
    # per-slide verdicts, reason codes, and cohort counts (report-export: siblings agree).
    tele, _ = _run_cohort(tmp_path, ["a", "b", "c"])
    run = json.loads(export_report(tele, fmt="json"))["runs"][0]
    html_doc = export_report(tele, fmt="html")

    for outcome, n in run["counts"].items():
        assert f"{outcome}={n}" in html_doc  # the HTML counts line carries the same tallies
    for slide in run["slides"]:
        assert slide["slide_stem"] in html_doc
        assert slide["outcome"] in html_doc
        assert slide["reason_code"] in html_doc


def test_empty_telemetry_exports_cleanly(tmp_path: Path) -> None:
    # The JSON sibling is now the versioned snapshot: an empty telemetry dir yields the
    # schema version, the agent roster, and an empty runs list (report-export: JSON is the
    # versioned snapshot).
    doc = json.loads(export_report(tmp_path / "empty", fmt="json"))
    assert doc["schema_version"] == SNAPSHOT_SCHEMA_VERSION
    assert doc["runs"] == []
    assert "No runs recorded" in export_report(tmp_path / "empty", fmt="html")
