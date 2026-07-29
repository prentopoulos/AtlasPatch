"""The structural-validity predicate over AtlasPatch HDF5 outputs (task 3.1).

This is the single predicate used at two call sites (design D4): the planner calls it
before dispatch (to decide skip-if-valid) and the scheduler calls it after execution
(to verify). It is a pure function of on-disk state with no side effects, so identical
on-disk state always yields an identical verdict (output-validation spec).

It reads the documented HDF5 format only and imports no ``atlas_patch`` internals: the
canonical output is ``<output_dir>/patches/<stem>.h5`` with a ``coords`` dataset
``(N, >=2)``, required integer file/coords attrs ``patch_size``, ``patch_size_level0``,
``target_magnification``, and, for feature output, ``features/<encoder>`` datasets
``(N, D)`` row-aligned to coords. AtlasPatch validates row alignment but never checks
for NaNs — that check is genuinely additive here (design grounding facts).
"""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np

from atlas_conductor.contracts import (
    Geometry,
    ReasonCode,
    RequestedOutput,
    Verdict,
)

# Mirrors atlas_patch.utils.feature_h5.REQUIRED_PATCH_FILE_ATTRS without importing it,
# honoring the no-reach-into-pipeline invariant.
_REQUIRED_INT_ATTRS = ("patch_size", "patch_size_level0", "target_magnification")

_VALID = Verdict(valid=True, reason=ReasonCode.VALID)


def patch_h5_path(output_dir: Path, slide_stem: str) -> Path:
    """The canonical HDF5 path for a slide stem (mirrors atlas_patch paths)."""
    return Path(output_dir) / "patches" / f"{slide_stem}.h5"


def feature_dataset_key(encoder: str) -> str:
    """The features dataset key for an encoder (mirrors patch_feature_dataset_key)."""
    return f"features/{encoder.strip().lower()}"


def validate_output(
    h5_path: Path,
    geometry: Geometry,
    requested_output: RequestedOutput,
    encoders: tuple[str, ...] = (),
) -> Verdict:
    """Return the structural-validity verdict for one slide's requested output.

    Pure and side-effect free. The reason code on failure distinguishes missing vs
    corrupt vs geometry-mismatch vs missing-features vs row-mismatch vs NaN, which the
    planner and the decision trace render.
    """
    path = Path(h5_path)
    if not path.exists():
        return Verdict(False, ReasonCode.MISSING, f"no HDF5 at {path}")
    if path.stat().st_size == 0:
        return Verdict(False, ReasonCode.CORRUPT, f"zero-byte HDF5 at {path}")

    try:
        with h5py.File(path, "r") as handle:
            coords_verdict = _check_coords(handle)
            if coords_verdict is not None:
                return coords_verdict

            geometry_verdict = _check_geometry(handle, geometry)
            if geometry_verdict is not None:
                return geometry_verdict

            if requested_output is RequestedOutput.FEATURES:
                coords_rows = int(handle["coords"].shape[0])
                for encoder in encoders:
                    feature_verdict = _check_features(handle, encoder, coords_rows)
                    if feature_verdict is not None:
                        return feature_verdict
    except OSError as exc:
        return Verdict(False, ReasonCode.CORRUPT, f"cannot open HDF5: {exc}")

    return _VALID


def _check_coords(handle: h5py.File) -> Verdict | None:
    coords = handle.get("coords")
    if not isinstance(coords, h5py.Dataset):
        return Verdict(False, ReasonCode.NO_COORDS, "coords dataset missing")
    if coords.ndim != 2 or coords.shape[1] < 2:
        return Verdict(False, ReasonCode.NO_COORDS, f"coords has unexpected shape {coords.shape}")
    if coords.shape[0] == 0:
        return Verdict(False, ReasonCode.NO_COORDS, "coords is empty")
    return None


def _read_int_attr(handle: h5py.File, key: str) -> int | None:
    """Read a required int attr from the file or the coords dataset (either carries it)."""
    for source in (handle.attrs, handle["coords"].attrs):
        if key in source:
            try:
                return int(source[key])
            except (TypeError, ValueError):
                return None
    return None


def _check_geometry(handle: h5py.File, geometry: Geometry) -> Verdict | None:
    attrs: dict[str, int] = {}
    for key in _REQUIRED_INT_ATTRS:
        value = _read_int_attr(handle, key)
        if value is None:
            return Verdict(False, ReasonCode.MISSING_ATTRS, f"required attr '{key}' missing")
        attrs[key] = value
    if attrs["patch_size"] != geometry.patch_size:
        return Verdict(
            False,
            ReasonCode.GEOMETRY_MISMATCH,
            f"patch_size {attrs['patch_size']} != requested {geometry.patch_size}",
        )
    if attrs["target_magnification"] != geometry.target_mag:
        return Verdict(
            False,
            ReasonCode.GEOMETRY_MISMATCH,
            f"target_magnification {attrs['target_magnification']} != "
            f"requested {geometry.target_mag}",
        )
    return None


def _check_features(handle: h5py.File, encoder: str, coords_rows: int) -> Verdict | None:
    dataset = handle.get(feature_dataset_key(encoder))
    if not isinstance(dataset, h5py.Dataset):
        return Verdict(False, ReasonCode.MISSING_FEATURES, f"features/{encoder} missing")
    if dataset.ndim != 2:
        return Verdict(
            False,
            ReasonCode.MISSING_FEATURES,
            f"features/{encoder} has unexpected shape {dataset.shape}",
        )
    if dataset.shape[0] != coords_rows:
        return Verdict(
            False,
            ReasonCode.ROW_MISMATCH,
            f"features/{encoder} rows {dataset.shape[0]} != coords rows {coords_rows}",
        )
    if _has_nan(dataset):
        return Verdict(False, ReasonCode.NAN_FEATURES, f"features/{encoder} contains NaN")
    return None


def _has_nan(dataset: h5py.Dataset) -> bool:
    """Stream the dataset in row chunks so a large embedding matrix is never fully resident."""
    if not np.issubdtype(dataset.dtype, np.floating):
        return False
    rows = dataset.shape[0]
    chunk = 4096
    for start in range(0, rows, chunk):
        block = dataset[start : start + chunk]
        if np.isnan(block).any():
            return True
    return False
