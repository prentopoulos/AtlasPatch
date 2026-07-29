"""Run-wiring tests for lineage: off by default, and additive when enabled (task 3.3).

Asserts the design D-LIN-7 invariant — lineage is recorded strictly after the scheduler
returns and writes only a sibling artifact, so enabling it changes no dispatch/output/telemetry
result. The default fake adapter is deterministic (seed 0, sorted stems), so two runs of the
same config produce byte-identical HDF5 outputs; enabling lineage must not perturb them.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import Geometry, RequestedOutput
from atlas_conductor.lineage.manifest import MANIFEST_RELATIVE_PATH
from atlas_conductor.run import run_job
from atlas_conductor.telemetry import JsonlTelemetrySink

_FAMILIES = (
    "jobs",
    "slide_stage_outcomes",
    "validation_results",
    "agent_events",
    "message_flow",
)


def _make_cohort(root: Path, stems: list[str]) -> Path:
    cohort = root / "cohort"
    cohort.mkdir(parents=True, exist_ok=True)
    for stem in stems:
        (cohort / f"{stem}.svs").write_bytes(f"wsi-{stem}".encode())
    return cohort


def _config(cohort: Path, out: Path, *, lineage: str | None) -> JobConfig:
    return JobConfig(
        input_dir=cohort,
        output_dir=out,
        requested_output=RequestedOutput.FEATURES,
        geometry=Geometry(patch_size=256, target_mag=20),
        encoders=("resnet50",),
        lineage_backend=lineage,
    )


def _hash_outputs(out: Path) -> dict[str, str]:
    return {
        h5.name: hashlib.sha256(h5.read_bytes()).hexdigest()
        for h5 in sorted((out / "patches").glob("*.h5"))
    }


def test_lineage_off_by_default_writes_no_artifact(tmp_path: Path) -> None:
    cohort = _make_cohort(tmp_path, ["slide_a", "slide_b"])
    out = tmp_path / "out"
    run_job(_config(cohort, out, lineage=None), JsonlTelemetrySink(out / "telemetry"))
    assert not (out / "lineage").exists()  # nothing written when lineage is off


def test_enabling_lineage_does_not_change_run_outputs(tmp_path: Path) -> None:
    cohort = _make_cohort(tmp_path, ["slide_a", "slide_b", "slide_c"])

    out_off = tmp_path / "off"
    off_sink = JsonlTelemetrySink(out_off / "telemetry")
    run_job(_config(cohort, out_off, lineage=None), off_sink)

    out_on = tmp_path / "on"
    on_sink = JsonlTelemetrySink(out_on / "telemetry")
    run_job(_config(cohort, out_on, lineage="manifest"), on_sink)

    # Produced HDF5 outputs are byte-identical — dispatch/validation/recovery were untouched.
    assert _hash_outputs(out_on) == _hash_outputs(out_off)

    # Telemetry volume per family is identical — no family gained or lost a row.
    for family in _FAMILIES:
        assert len(on_sink.read_family(family)) == len(off_sink.read_family(family))

    # The only difference is the additive sibling manifest, present solely in the on-run.
    assert (out_on / MANIFEST_RELATIVE_PATH).is_file()
    assert not (out_off / "lineage").exists()

    # Lineage is a sibling of telemetry, not a sixth telemetry family.
    assert not (out_on / "telemetry" / "lineage.jsonl").exists()
    manifest_records = (out_on / MANIFEST_RELATIVE_PATH).read_text(encoding="utf-8").splitlines()
    assert len(manifest_records) == 3  # one per produced output


def _read_manifest(out: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (out / MANIFEST_RELATIVE_PATH).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _input_output_pairs(rows: list[dict[str, Any]]) -> set[tuple[tuple[str, ...], str]]:
    # Per-run pseudonyms differ across runs (unlinkable by design), so compare on the
    # content hashes, which are what "reproduce identically" and "detect change" are about.
    return {(tuple(row["input_sha256"]), str(row["output_sha256"])) for row in rows}


def test_config_driven_lineage_content_addresses_and_detects_change(tmp_path: Path) -> None:
    # A fake-adapter run with `lineage: {backend: manifest}` (task 6.2 end-to-end).
    cohort = _make_cohort(tmp_path, ["slide_a", "slide_b"])
    out = tmp_path / "out"
    config = _config(cohort, out, lineage="manifest")

    run_job(config, JsonlTelemetrySink(out / "telemetry"))
    first_rows = _read_manifest(out)

    # Every produced output is content-addressed (input + output SHA-256, fingerprint).
    assert len(first_rows) == 2
    for row in first_rows:
        assert len(str(row["output_sha256"])) == 64
        assert row["input_sha256"] and all(len(h) == 64 for h in row["input_sha256"])
        assert row["config_fingerprint"]
    first_pairs = _input_output_pairs(first_rows)

    # Re-record via a second run over unchanged bytes: the content-hash pairs reproduce exactly.
    run_job(config, JsonlTelemetrySink(out / "telemetry2"))
    second_rows = _read_manifest(out)[len(first_rows) :]  # only the newly appended records
    assert _input_output_pairs(second_rows) == first_pairs

    # Change one input's bytes and record again: a new input hash appears, absent before.
    (cohort / "slide_a.svs").write_bytes(b"mutated-wsi-bytes")
    before_mutation = len(_read_manifest(out))
    run_job(config, JsonlTelemetrySink(out / "telemetry3"))
    third_rows = _read_manifest(out)[before_mutation:]
    prior_input_hashes = {h for row in first_rows for h in row["input_sha256"]}
    new_input_hashes = {h for row in third_rows for h in row["input_sha256"]}
    assert new_input_hashes - prior_input_hashes  # slide_a's mutated bytes hash is new
