"""Helpers to build AtlasPatch-shaped HDF5 fixtures for validator tests.

These write real HDF5 files matching (or deliberately violating) the documented
format, so the validator's structural checks run against genuine files rather than
mocks.
"""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np


def write_patch_h5(
    path: Path,
    *,
    n: int = 8,
    patch_size: int = 256,
    target_mag: int = 20,
    encoders: tuple[str, ...] = (),
    feature_dim: int = 16,
    feature_rows: int | None = None,
    inject_nan: bool = False,
    omit_coords: bool = False,
    empty_coords: bool = False,
    omit_attrs: bool = False,
) -> Path:
    """Write a patch HDF5, optionally violating one structural invariant."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = feature_rows if feature_rows is not None else n
    with h5py.File(path, "w") as handle:
        if not omit_coords:
            data = (
                np.zeros((0, 5), dtype=np.int64)
                if empty_coords
                else np.ones((n, 5), dtype=np.int64)
            )
            coords = handle.create_dataset("coords", data=data)
            if not omit_attrs:
                for attr, value in (
                    ("patch_size", patch_size),
                    ("patch_size_level0", patch_size),
                    ("target_magnification", target_mag),
                ):
                    handle.attrs[attr] = int(value)
                    coords.attrs[attr] = int(value)
        if encoders:
            grp = handle.create_group("features")
            for enc in encoders:
                features = np.ones((rows, feature_dim), dtype=np.float32)
                if inject_nan:
                    features[0, 0] = np.nan
                grp.create_dataset(enc.strip().lower(), data=features)
    return path


def write_corrupt_h5(path: Path) -> Path:
    """Write a non-HDF5 file at ``path`` (opens as garbage)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not an hdf5 file at all")
    return path
