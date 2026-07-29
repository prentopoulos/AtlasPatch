"""Run-wiring tests for lineage: off by default, and additive when enabled (task 3.3).

Asserts the design D-LIN-7 invariant — lineage is recorded strictly after the scheduler
returns and writes only a sibling artifact, so enabling it changes no dispatch/output/telemetry
result. The default fake adapter is deterministic (seed 0, sorted stems), so two runs of the
same config produce byte-identical HDF5 outputs; enabling lineage must not perturb them.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

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
