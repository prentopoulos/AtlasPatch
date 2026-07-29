"""Tests for the opt-in DVC lineage backend (task 5.3).

The ``dvc`` invocation is faked (an injected runner), so these run with no ``dvc`` binary — as
CI does. They assert a ``dvc.yaml`` stage + ``.dvc`` pointers are produced, carry the same
hashes as the manifest backend, embed no raw stem/WSI filename in any tracked path, and that
the backend never issues a ``dvc push``.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import Geometry, RequestedOutput
from atlas_conductor.lineage import ManifestLineage, from_plan
from atlas_conductor.lineage.dvc_backend import DVC_SUBDIR, DvcLineage
from atlas_conductor.run import run_job
from atlas_conductor.scheduler import RunResult
from atlas_conductor.telemetry import InMemoryTelemetrySink

_RAW_STEM = "MRN-00456789"  # a raw stem that is itself an identifier


class _RecordingRunner:
    """A fake ``dvc`` runner capturing every invocation instead of shelling out."""

    def __init__(self) -> None:
        self.calls: list[tuple[Sequence[str], Path]] = []

    def __call__(self, args: Sequence[str], cwd: Path) -> None:
        self.calls.append((list(args), cwd))


def _run(tmp_path: Path, stems: list[str]) -> tuple[JobConfig, RunResult]:
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    for stem in stems:
        (cohort / f"{stem}.svs").write_bytes(f"wsi-{stem}".encode())
    config = JobConfig(
        input_dir=cohort,
        output_dir=tmp_path / "out",
        requested_output=RequestedOutput.FEATURES,
        geometry=Geometry(patch_size=256, target_mag=20),
        encoders=("resnet50",),
    )
    result = run_job(config, InMemoryTelemetrySink())
    return config, result


def test_dvc_backend_produces_stage_and_pointers(tmp_path: Path) -> None:
    config, result = _run(tmp_path, ["slide_a", "slide_b"])
    runner = _RecordingRunner()

    outcome = DvcLineage(runner=runner).record(from_plan(result.plan, config))

    dvc_dir = config.output_dir / DVC_SUBDIR
    assert (dvc_dir / "dvc.yaml").is_file()
    pointers = sorted(dvc_dir.glob("*.h5.dvc"))
    assert len(pointers) == 2
    # The stage references every produced output by pseudonym.
    stage_text = (dvc_dir / "dvc.yaml").read_text(encoding="utf-8")
    for record in outcome.records:
        assert f"{record.slide_stem}.h5" in stage_text


def test_dvc_and_manifest_agree_on_hashes(tmp_path: Path) -> None:
    config, result = _run(tmp_path, ["slide_a", "slide_b"])

    manifest_records = {
        r.slide_stem: r for r in ManifestLineage().record(from_plan(result.plan, config)).records
    }
    dvc_records = {
        r.slide_stem: r
        for r in DvcLineage(runner=_RecordingRunner())
        .record(from_plan(result.plan, config))
        .records
    }

    assert manifest_records.keys() == dvc_records.keys()
    for stem, m in manifest_records.items():
        assert dvc_records[stem].output_sha256 == m.output_sha256
        assert dvc_records[stem].input_sha256 == m.input_sha256
        assert dvc_records[stem].config_fingerprint == m.config_fingerprint

    # The pointer files carry those same output hashes.
    dvc_dir = config.output_dir / DVC_SUBDIR
    for stem, record in dvc_records.items():
        pointer = (dvc_dir / f"{stem}.h5.dvc").read_text(encoding="utf-8")
        assert record.output_sha256 in pointer


def test_dvc_tracked_paths_carry_no_raw_identifier(tmp_path: Path) -> None:
    config, result = _run(tmp_path, [_RAW_STEM])

    DvcLineage(runner=_RecordingRunner()).record(from_plan(result.plan, config))

    dvc_dir = config.output_dir / DVC_SUBDIR
    for tracked in dvc_dir.rglob("*"):
        if tracked.is_file():
            # No raw stem in a tracked path...
            assert _RAW_STEM not in tracked.name
            # ...and none inside a tracked file (dvc.yaml fields, .dvc pointers).
            assert _RAW_STEM not in tracked.read_text(encoding="utf-8")


def test_dvc_backend_never_pushes(tmp_path: Path) -> None:
    config, result = _run(tmp_path, ["slide_a"])
    runner = _RecordingRunner()

    DvcLineage(runner=runner).record(from_plan(result.plan, config))

    assert runner.calls  # the injected runner was exercised
    for args, _cwd in runner.calls:
        assert "push" not in args  # never egresses to a DVC remote
        assert "add" not in args  # never copies pixels into a DVC cache


def test_dvc_backend_writes_files_without_a_runner(tmp_path: Path) -> None:
    # Default (no runner): produces committable files and touches no dvc binary.
    config, result = _run(tmp_path, ["slide_a"])
    outcome = DvcLineage().record(from_plan(result.plan, config))
    assert outcome.manifest_path is not None and outcome.manifest_path.is_file()
    assert outcome.tracked_paths
