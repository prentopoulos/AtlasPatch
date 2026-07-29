"""Unit tests for the data-lineage model, hashing, and the default manifest backend.

Covers tasks 1.1–1.3 (record shape, streaming hash, config fingerprint, tool-version
fallback) and 2.2–2.4 (manifest backend, PHI routing, artifact resolution). The DVC backend,
run-wiring, and CLI have their own suites.
"""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path

import pytest

from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import Geometry, RequestedOutput
from atlas_conductor.governance.phi import is_pseudonym, pseudonymize_stem
from atlas_conductor.lineage import (
    LineagePhiError,
    LineageRecord,
    ManifestLineage,
    assert_lineage_phi_free,
    config_fingerprint,
    from_output_dir,
    from_plan,
    sha256_file,
    tool_version,
)
from atlas_conductor.lineage.manifest import MANIFEST_RELATIVE_PATH
from atlas_conductor.run import plan_job, run_job
from atlas_conductor.telemetry import InMemoryTelemetrySink, JsonlTelemetrySink


def _make_cohort(root: Path, stems: list[str]) -> Path:
    cohort = root / "cohort"
    cohort.mkdir(parents=True, exist_ok=True)
    for stem in stems:
        (cohort / f"{stem}.svs").write_bytes(f"wsi-bytes-of-{stem}".encode())
    return cohort


def _features_config(cohort: Path, out: Path, patch_size: int = 256) -> JobConfig:
    return JobConfig(
        input_dir=cohort,
        output_dir=out,
        requested_output=RequestedOutput.FEATURES,
        geometry=Geometry(patch_size=patch_size, target_mag=20),
        encoders=("resnet50",),
    )


# -- task 1.2: streaming hash ----------------------------------------------------------------


def test_sha256_file_matches_hashlib_and_is_stable(tmp_path: Path) -> None:
    blob = tmp_path / "blob.bin"
    blob.write_bytes(b"a" * (3 * (1 << 20) + 17))  # spans several 1 MiB chunks
    import hashlib

    expected = hashlib.sha256(blob.read_bytes()).hexdigest()
    assert sha256_file(blob) == expected
    assert sha256_file(blob) == sha256_file(blob)  # stable across calls


def test_sha256_file_detects_a_byte_change(tmp_path: Path) -> None:
    blob = tmp_path / "blob.bin"
    blob.write_bytes(b"original")
    before = sha256_file(blob)
    blob.write_bytes(b"changed!")
    assert sha256_file(blob) != before


# -- task 1.2: config fingerprint ------------------------------------------------------------


def test_config_fingerprint_is_stable_for_equal_config(tmp_path: Path) -> None:
    cfg = _features_config(tmp_path / "c", tmp_path / "o")
    again = _features_config(tmp_path / "c", tmp_path / "o")
    assert config_fingerprint(cfg) == config_fingerprint(again)


def test_config_fingerprint_changes_with_geometry_and_encoders(tmp_path: Path) -> None:
    base = _features_config(tmp_path / "c", tmp_path / "o", patch_size=256)
    bigger = _features_config(tmp_path / "c", tmp_path / "o", patch_size=512)
    assert config_fingerprint(base) != config_fingerprint(bigger)

    more_encoders = JobConfig(
        input_dir=base.input_dir,
        output_dir=base.output_dir,
        requested_output=RequestedOutput.FEATURES,
        geometry=base.geometry,
        encoders=("resnet50", "uni"),
    )
    assert config_fingerprint(base) != config_fingerprint(more_encoders)


# -- task 1.3: tool version fallback ---------------------------------------------------------


def test_tool_version_reads_distribution_metadata() -> None:
    assert tool_version()  # non-empty; the installed atlas-patch version in dev/CI


def test_tool_version_falls_back_when_metadata_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(_name: str) -> str:
        raise importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(importlib.metadata, "version", _raise)
    assert tool_version() == "unknown"


# -- task 2.3: PHI routing -------------------------------------------------------------------


def test_records_identify_slides_only_by_pseudonym(tmp_path: Path) -> None:
    # A raw stem that is itself an identifier shape.
    cohort = _make_cohort(tmp_path, ["00123456"])
    out = tmp_path / "out"
    config = _features_config(cohort, out)
    result = run_job(config, InMemoryTelemetrySink())
    plan = result.plan

    records = ManifestLineage().record(from_plan(plan, config)).records
    assert records
    for record in records:
        assert is_pseudonym(record.slide_stem)
        assert record.slide_stem == pseudonymize_stem("00123456", plan.job_id)
        assert "00123456" != record.slide_stem


def test_leaked_identifier_in_a_field_is_rejected() -> None:
    leaked = LineageRecord(
        job_id="job_1",
        slide_stem="MRN 00987654",  # a non-pseudonym stem bearing a Safe-Harbor shape
        input_sha256=(),
        output_sha256="0" * 64,
        config_fingerprint="deadbeef",
        tool_version="1.2.3",
    )
    with pytest.raises(LineagePhiError):
        assert_lineage_phi_free(leaked)


def test_pseudonym_stem_passes_the_gate() -> None:
    ok = LineageRecord(
        job_id="job_1",
        slide_stem=pseudonymize_stem("patient-a", "job_1"),
        input_sha256=(),
        output_sha256="0" * 64,
        config_fingerprint="deadbeef",
        tool_version="1.2.3",
    )
    assert_lineage_phi_free(ok)  # does not raise


# -- tasks 1.1/2.2/2.4: manifest records over a real run -------------------------------------


def test_manifest_content_addresses_every_produced_output(tmp_path: Path) -> None:
    cohort = _make_cohort(tmp_path, ["slide_a", "slide_b", "slide_c"])
    out = tmp_path / "out"
    config = _features_config(cohort, out)
    result = run_job(config, InMemoryTelemetrySink())

    outcome = ManifestLineage().record(from_plan(result.plan, config))

    # One record per produced output HDF5, each fully content-addressed.
    assert len(outcome.records) == 3
    for record in outcome.records:
        assert len(record.output_sha256) == 64
        assert record.input_sha256 and all(len(h) == 64 for h in record.input_sha256)
        assert record.config_fingerprint == config_fingerprint(config)
        assert record.tool_version
        assert record.job_id == result.plan.job_id

    # The manifest is a JSONL sibling of telemetry and round-trips.
    assert outcome.manifest_path == out / MANIFEST_RELATIVE_PATH
    lines = outcome.manifest_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    assert all(json.loads(line)["slide_stem"].startswith("slide_") for line in lines)


def test_rerecording_reproduces_hashes_until_an_input_changes(tmp_path: Path) -> None:
    cohort = _make_cohort(tmp_path, ["slide_a", "slide_b"])
    out = tmp_path / "out"
    config = _features_config(cohort, out)
    result = run_job(config, InMemoryTelemetrySink())

    first = {
        r.slide_stem: r for r in ManifestLineage().record(from_plan(result.plan, config)).records
    }

    # Re-record unchanged: identical input+output hashes (recorded_at may differ).
    second = {
        r.slide_stem: r for r in ManifestLineage().record(from_plan(result.plan, config)).records
    }
    for stem, rec in first.items():
        assert second[stem].input_sha256 == rec.input_sha256
        assert second[stem].output_sha256 == rec.output_sha256

    # Change one input's bytes and re-record: its input hash moves, the sibling's does not.
    (cohort / "slide_a.svs").write_bytes(b"mutated-wsi-bytes")
    third = {
        r.slide_stem: r for r in ManifestLineage().record(from_plan(result.plan, config)).records
    }
    stem_a = pseudonymize_stem("slide_a", result.plan.job_id)
    stem_b = pseudonymize_stem("slide_b", result.plan.job_id)
    assert third[stem_a].input_sha256 != first[stem_a].input_sha256
    assert third[stem_b].input_sha256 == first[stem_b].input_sha256


def test_from_output_dir_resolves_post_hoc_from_telemetry(tmp_path: Path) -> None:
    cohort = _make_cohort(tmp_path, ["slide_a", "slide_b"])
    out = tmp_path / "out"
    config = _features_config(cohort, out)
    sink = JsonlTelemetrySink(out / "telemetry")
    run_job(config, sink)

    # Post-hoc: resolve purely from output_dir + telemetry (no plan in hand).
    resolved = from_output_dir(out)
    outcome = ManifestLineage().record(resolved)

    stems = {r.slide_stem for r in outcome.records}
    job_id = sink.read_family("jobs")[-1]["job_id"]
    assert stems == {pseudonymize_stem(s, job_id) for s in ("slide_a", "slide_b")}
    # Inputs were resolved from the recorded input_dir, so hashes are present.
    assert all(r.input_sha256 for r in outcome.records)


def test_from_plan_skips_slides_with_no_output(tmp_path: Path) -> None:
    cohort = _make_cohort(tmp_path, ["slide_a"])
    out = tmp_path / "out"
    config = _features_config(cohort, out)
    # A dry-run plan: no dispatch, so no HDF5 exists yet.
    plan = plan_job(config, InMemoryTelemetrySink())
    resolved = from_plan(plan, config)
    assert resolved.artifacts == ()  # nothing produced → nothing to content-address
