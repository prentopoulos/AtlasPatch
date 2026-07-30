"""Tests for the ``atlaspatch-conduct export-dossier`` subcommand (task 5.1; design D-CMP-5).

The subcommand renders the run-scoped compliance evidence bundle in JSON and HTML from a
recorded run's telemetry directory (read-only, mirroring ``export-report``).
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from atlas_conductor import cli as cli_mod
from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import Geometry, RequestedOutput
from atlas_conductor.governance.audit import JsonlAuditTrail
from atlas_conductor.run import run_job
from atlas_conductor.telemetry import JsonlTelemetrySink


def _run(tmp_path: Path) -> Path:
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    for stem in ("slide_a", "slide_b"):
        (cohort / f"{stem}.svs").write_bytes(f"wsi-{stem}".encode())
    tele = tmp_path / "tele"
    config = JobConfig(
        input_dir=cohort,
        output_dir=tmp_path / "out",
        requested_output=RequestedOutput.FEATURES,
        geometry=Geometry(patch_size=256, target_mag=20),
        encoders=("resnet50",),
    )
    run_job(config, JsonlTelemetrySink(tele), audit=JsonlAuditTrail(tele / "audit.jsonl"))
    return tele


def test_export_dossier_renders_json(tmp_path: Path) -> None:
    tele = _run(tmp_path)
    result = CliRunner().invoke(cli_mod.cli, ["export-dossier", str(tele), "--format", "json"])
    assert result.exit_code == 0, result.output
    doc = json.loads(result.output)
    assert "audit_chain" in doc and doc["audit_chain"]["intact"] is True
    assert doc["runs"] and doc["controls"]["well_formed"] is True


def test_export_dossier_renders_html(tmp_path: Path) -> None:
    tele = _run(tmp_path)
    result = CliRunner().invoke(cli_mod.cli, ["export-dossier", str(tele), "--format", "html"])
    assert result.exit_code == 0, result.output
    assert "<!doctype html>" in result.output.lower()
    assert "compliance evidence" in result.output.lower()
    assert "<img" not in result.output.lower() and "<script" not in result.output.lower()
