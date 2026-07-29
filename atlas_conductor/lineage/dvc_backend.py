"""The opt-in DVC lineage backend (D-LIN-4, task 5.2).

``DvcLineage`` turns a finished run into a **version-controllable** provenance trail: a
``dvc.yaml`` stage plus one ``.dvc`` pointer per output HDF5, carrying the same content hashes
and pseudonyms the default :class:`ManifestLineage` records (the spec requires the two backends
to agree). Committing those files to Git is what makes Git history the lineage record.

Two invariants shape the implementation:

* **PHI-free tracked paths (D-LIN-6).** Every tracked identifier is the ``slide_<hex>``
  pseudonym and every path is relative; inputs are referenced by content **hash**, never by
  filename. No raw stem or WSI filename lands in a ``.dvc`` pointer, a ``dvc.yaml`` field, or a
  lock entry. Each record is run through :func:`assert_lineage_phi_free` before it is written.
* **No pixels move, nothing is pushed (D-LIN-4/5).** The backend writes YAML with stdlib and
  never copies a WSI/HDF5 into a DVC cache; it runs no ``dvc push``. It does not even need the
  ``dvc`` binary — it *produces committable files* and leaves committing/tracking to the human
  or CI (design non-goal: no auto-commit). An operator who wants ``dvc`` to also register the
  stage may inject a ``runner``; ``dvc``/``subprocess`` are then touched only inside the
  runner's call — never at import — so the core import graph stays DVC-free (import-guard test).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from atlas_conductor.lineage.base import (
    LineageBackend,
    LineageInput,
    LineageRecord,
    LineageResult,
    assert_lineage_phi_free,
    build_records,
)

#: A DVC runner shells the ``dvc`` CLI: ``runner(dvc_args, cwd)``. Injected in tests; the
#: default is ``None`` (no shell — the backend only writes committable files).
DvcRunner = Callable[[Sequence[str], Path], None]

DVC_SUBDIR = Path("lineage") / "dvc"
_STAGE_NAME = "atlaspatch_lineage"


class DvcLineage(LineageBackend):
    """Write DVC pointers + a ``dvc.yaml`` stage as a committable, PHI-free lineage record."""

    name = "dvc"

    def __init__(self, runner: DvcRunner | None = None) -> None:
        self._runner = runner

    def record(self, run: LineageInput) -> LineageResult:
        records = build_records(run)
        dvc_dir = Path(run.output_dir) / DVC_SUBDIR
        dvc_dir.mkdir(parents=True, exist_ok=True)

        tracked: list[Path] = []
        for record in records:
            assert_lineage_phi_free(record)  # fail closed before any tracked path is written
            pointer = dvc_dir / f"{record.slide_stem}.h5.dvc"
            pointer.write_text(_render_pointer(record), encoding="utf-8")
            tracked.append(pointer)

        stage_path = dvc_dir / "dvc.yaml"
        stage_path.write_text(_render_stage(records), encoding="utf-8")
        tracked.append(stage_path)

        self._maybe_track(dvc_dir, stage_path)
        return LineageResult(
            backend=self.name,
            records=tuple(records),
            manifest_path=stage_path,
            tracked_paths=tuple(tracked),
        )

    def _maybe_track(self, dvc_dir: Path, stage_path: Path) -> None:
        """Optionally hand the stage to ``dvc`` — read-only, never ``push`` (D-LIN-4/5).

        Only runs when a ``runner`` was injected; the default backend writes files and stops,
        leaving commit/track to the operator. ``dvc``/``subprocess`` are touched only here.
        """
        if self._runner is None:
            return
        # A read-only status query on the just-written stage — deliberately never a `push`,
        # `add`, or `commit`, so no pixels are moved and nothing egresses to a DVC remote.
        self._runner(["status", stage_path.name], dvc_dir)


def _render_pointer(record: LineageRecord) -> str:
    """Render one ``.dvc`` pointer: the output's content hash under a pseudonymized path.

    DVC-shaped YAML (``outs:`` list) but keyed on the D-LIN-2 SHA-256 rather than DVC's default
    MD5, and referencing the output only by its ``slide_<hex>`` pseudonym so no raw filename is
    tracked. Inputs are recorded by content hash, again with no filename.
    """
    lines = [
        "outs:",
        f"- sha256: {record.output_sha256}",
        f"  path: {record.slide_stem}.h5",
        "  meta:",
        f"    config_fingerprint: {record.config_fingerprint}",
        f"    tool_version: {record.tool_version}",
    ]
    if record.input_sha256:
        lines.append("    input_sha256:")
        lines.extend(f"    - {digest}" for digest in record.input_sha256)
    return "\n".join(lines) + "\n"


def _render_stage(records: Sequence[LineageRecord]) -> str:
    """Render the one-per-run ``dvc.yaml`` stage: deps = input hashes + config, outs = outputs.

    Deps reference the config fingerprint and each distinct input content hash (never a
    filename); outs are the pseudonymized output identifiers. The result is valid,
    human-readable, Git-versionable YAML that carries no raw identifier.
    """
    fingerprints = sorted({r.config_fingerprint for r in records})
    input_hashes = sorted({digest for r in records for digest in r.input_sha256})
    outs = sorted(f"{r.slide_stem}.h5" for r in records)

    lines = ["stages:", f"  {_STAGE_NAME}:", "    cmd: atlaspatch-conduct lineage", "    deps:"]
    lines.extend(f"    - config-fingerprint:{fp}" for fp in fingerprints)
    lines.extend(f"    - input-sha256:{digest}" for digest in input_hashes)
    lines.append("    outs:")
    lines.extend(f"    - {out}" for out in outs)
    return "\n".join(lines) + "\n"
