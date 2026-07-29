"""Tests for the ``atlaspatch-conduct lineage`` subcommand (task 4.2).

The subcommand records a manifest over a finished fake-adapter run and leaves the run's HDF5s
and telemetry unmodified. It imports no ``dvc`` at module level (the guard test in
``test_gui_guards.py`` covers the whole core CLI import graph).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from click.testing import CliRunner

from atlas_conductor import cli as cli_mod
from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import Geometry, RequestedOutput
from atlas_conductor.lineage.manifest import MANIFEST_RELATIVE_PATH
from atlas_conductor.run import run_job
from atlas_conductor.telemetry import JsonlTelemetrySink


def _run(tmp_path: Path, stems: list[str]) -> Path:
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    for stem in stems:
        (cohort / f"{stem}.svs").write_bytes(f"wsi-{stem}".encode())
    out = tmp_path / "out"
    config = JobConfig(
        input_dir=cohort,
        output_dir=out,
        requested_output=RequestedOutput.FEATURES,
        geometry=Geometry(patch_size=256, target_mag=20),
        encoders=("resnet50",),
    )
    run_job(config, JsonlTelemetrySink(out / "telemetry"))
    return out


def _digest_tree(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_lineage_subcommand_records_a_manifest(tmp_path: Path) -> None:
    out = _run(tmp_path, ["slide_a", "slide_b"])

    result = CliRunner().invoke(cli_mod.cli, ["lineage", str(out)])
    assert result.exit_code == 0, result.output
    assert "recorded 2 lineage record(s) via manifest" in result.output

    manifest = out / MANIFEST_RELATIVE_PATH
    assert manifest.is_file()
    assert len(manifest.read_text(encoding="utf-8").splitlines()) == 2


def test_lineage_subcommand_leaves_outputs_and_telemetry_unmodified(tmp_path: Path) -> None:
    out = _run(tmp_path, ["slide_a", "slide_b"])

    before_outputs = _digest_tree(out / "patches")
    before_telemetry = _digest_tree(out / "telemetry")

    result = CliRunner().invoke(cli_mod.cli, ["lineage", str(out)])
    assert result.exit_code == 0, result.output

    assert _digest_tree(out / "patches") == before_outputs  # HDF5s untouched
    assert _digest_tree(out / "telemetry") == before_telemetry  # telemetry untouched


def test_lineage_subcommand_errors_without_telemetry(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    (empty / "patches").mkdir(parents=True)

    result = CliRunner().invoke(cli_mod.cli, ["lineage", str(empty)])
    assert result.exit_code != 0
    assert "telemetry" in result.output.lower()
