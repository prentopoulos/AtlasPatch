"""Resolve a finished run into a :class:`LineageInput` (task 2.4, D-LIN-3/7).

Two read-only entry points, both using the same "observe a finished run" path the report and
GUI use — read ``output_dir`` (+ telemetry), touch nothing upstream:

* :func:`from_plan` — the in-process path used by ``run_job``: the reconciled plan already
  carries each slide's raw stem, input WSI, and expected HDF5 path, so the mapping is exact.
* :func:`from_output_dir` — the post-hoc path used by the ``lineage`` CLI subcommand over a
  completed run: the produced HDF5s under ``<output_dir>/patches`` are ground truth, and each
  is mapped back to its input WSI(s) via the ``input_dir`` recorded in the ``jobs`` telemetry.

Only produced outputs (an HDF5 that exists on disk) yield an artifact. An output whose input
WSI cannot be resolved is recorded with an empty input-hash tuple rather than failing the
whole manifest (D-LIN, "Telemetry may not name every input↔output pair").
"""

from __future__ import annotations

import json
from pathlib import Path

from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import STAGES_FOR_OUTPUT, Geometry, Plan, RequestedOutput
from atlas_conductor.lineage.base import ArtifactPair, LineageInput

_JOBS_FAMILY_FILE = "jobs.jsonl"


class LineageResolutionError(ValueError):
    """A finished run could not be resolved into lineage inputs (e.g. no telemetry)."""


def from_plan(plan: Plan, config: JobConfig) -> LineageInput:
    """Resolve the produced outputs of an in-hand ``plan`` into a :class:`LineageInput`.

    One artifact per slide whose terminal-stage HDF5 exists on disk, mapping the raw stem to
    its input WSI and produced HDF5 straight from the plan's targets.
    """
    terminal_stage = STAGES_FOR_OUTPUT[plan.requested_output][-1]
    artifacts: list[ArtifactPair] = []
    for node in plan.nodes_for(terminal_stage):
        output_h5 = node.target.expected_h5_path
        if not output_h5.exists():
            continue  # a blocked/failed slide produced no output to content-address
        artifacts.append(
            ArtifactPair(
                slide_stem=node.slide_stem,
                output_h5=output_h5,
                input_wsis=(node.target.wsi_path,) if node.target.wsi_path.exists() else (),
            )
        )
    return LineageInput(
        job_id=plan.job_id,
        output_dir=plan.output_dir,
        config=config,
        artifacts=tuple(artifacts),
    )


def from_output_dir(
    output_dir: str | Path, telemetry_dir: str | Path | None = None
) -> LineageInput:
    """Resolve a completed run's outputs post-hoc from ``output_dir`` + its telemetry.

    Reads the ``jobs`` telemetry to recover the ``job_id`` (needed to pseudonymize) and the
    run's config identity, discovers the produced HDF5s under ``<output_dir>/patches``, and
    maps each back to its input WSI(s) by globbing the recorded ``input_dir`` for the stem.
    Raises :class:`LineageResolutionError` when no ``jobs`` telemetry is present.
    """
    output_path = Path(output_dir)
    tele_dir = Path(telemetry_dir) if telemetry_dir is not None else output_path / "telemetry"
    job_row = _last_job_row(tele_dir)
    if job_row is None:
        raise LineageResolutionError(
            f"no '{_JOBS_FAMILY_FILE}' telemetry found under {tele_dir}; cannot resolve the "
            "job_id required to pseudonymize lineage records"
        )

    job_id = str(job_row["job_id"])
    config = _config_from_job_row(job_row, output_path)
    input_dir = Path(str(job_row.get("input_dir", ""))) if job_row.get("input_dir") else None

    patches_dir = output_path / "patches"
    artifacts: list[ArtifactPair] = []
    for output_h5 in sorted(patches_dir.glob("*.h5")):
        stem = output_h5.stem
        artifacts.append(
            ArtifactPair(
                slide_stem=stem,
                output_h5=output_h5,
                input_wsis=_resolve_inputs(input_dir, stem),
            )
        )
    return LineageInput(
        job_id=job_id,
        output_dir=output_path,
        config=config,
        artifacts=tuple(artifacts),
    )


def _resolve_inputs(input_dir: Path | None, stem: str) -> tuple[Path, ...]:
    """Return the input WSI file(s) for ``stem`` under ``input_dir`` (empty if unresolvable)."""
    if input_dir is None or not input_dir.is_dir():
        return ()
    matches = [
        candidate
        for candidate in sorted(input_dir.glob(f"{stem}.*"))
        if candidate.is_file() and candidate.suffix.lower() != ".h5"
    ]
    return tuple(matches)


def _last_job_row(telemetry_dir: Path) -> dict[str, object] | None:
    """Read the last ``jobs`` row (the run's final tallies) without mutating anything."""
    jobs_path = telemetry_dir / _JOBS_FAMILY_FILE
    if not jobs_path.is_file():
        return None
    last: dict[str, object] | None = None
    with jobs_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                last = json.loads(line)
    return last


def _config_from_job_row(job_row: dict[str, object], output_dir: Path) -> JobConfig:
    """Reconstruct the config identity from a ``jobs`` telemetry row.

    ``step_size`` is not persisted in telemetry, so the reconstructed geometry leaves it
    ``None`` — the fingerprint stays sensitive to patch size, magnification, encoders, and
    requested output, which is what the change-detection scenarios require.
    """
    encoders_field = str(job_row.get("encoders", "") or "")
    encoders = tuple(part for part in encoders_field.split(",") if part)
    return JobConfig(
        input_dir=Path(str(job_row.get("input_dir", ""))),
        output_dir=output_dir,
        requested_output=RequestedOutput(str(job_row["requested_output"])),
        geometry=Geometry(
            patch_size=int(str(job_row["patch_size"])),
            target_mag=int(str(job_row["target_mag"])),
            step_size=None,
        ),
        encoders=encoders,
    )
