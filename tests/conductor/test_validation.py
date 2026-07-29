"""Tests for the structural-validity predicate (task 3.3).

Covers the fully-valid case and every reason code the predicate distinguishes, using
real HDF5 fixtures. Also asserts the predicate is pure — same on-disk state yields the
same verdict at plan time and post-run (output-validation spec).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas_conductor.contracts import Geometry, ReasonCode, RequestedOutput
from atlas_conductor.validation import validate_output
from tests.conductor.h5_fixtures import write_corrupt_h5, write_patch_h5

GEOMETRY = Geometry(patch_size=256, target_mag=20)
ENC = ("resnet50",)


def test_fully_valid_features(tmp_path: Path) -> None:
    h5 = write_patch_h5(tmp_path / "s.h5", encoders=ENC)
    verdict = validate_output(h5, GEOMETRY, RequestedOutput.FEATURES, ENC)
    assert verdict.valid
    assert verdict.reason is ReasonCode.VALID


def test_fully_valid_coords_only(tmp_path: Path) -> None:
    h5 = write_patch_h5(tmp_path / "s.h5")
    verdict = validate_output(h5, GEOMETRY, RequestedOutput.COORDS)
    assert verdict.valid


def test_missing_file(tmp_path: Path) -> None:
    verdict = validate_output(tmp_path / "nope.h5", GEOMETRY, RequestedOutput.COORDS)
    assert not verdict.valid
    assert verdict.reason is ReasonCode.MISSING


def test_corrupt_file(tmp_path: Path) -> None:
    h5 = write_corrupt_h5(tmp_path / "bad.h5")
    verdict = validate_output(h5, GEOMETRY, RequestedOutput.COORDS)
    assert not verdict.valid
    assert verdict.reason is ReasonCode.CORRUPT


def test_zero_byte_file(tmp_path: Path) -> None:
    h5 = tmp_path / "empty.h5"
    h5.write_bytes(b"")
    verdict = validate_output(h5, GEOMETRY, RequestedOutput.COORDS)
    assert not verdict.valid
    assert verdict.reason is ReasonCode.CORRUPT


def test_missing_coords(tmp_path: Path) -> None:
    h5 = write_patch_h5(tmp_path / "s.h5", omit_coords=True)
    verdict = validate_output(h5, GEOMETRY, RequestedOutput.COORDS)
    assert not verdict.valid
    assert verdict.reason is ReasonCode.NO_COORDS


def test_empty_coords(tmp_path: Path) -> None:
    h5 = write_patch_h5(tmp_path / "s.h5", empty_coords=True)
    verdict = validate_output(h5, GEOMETRY, RequestedOutput.COORDS)
    assert not verdict.valid
    assert verdict.reason is ReasonCode.NO_COORDS


def test_missing_attrs(tmp_path: Path) -> None:
    h5 = write_patch_h5(tmp_path / "s.h5", omit_attrs=True)
    verdict = validate_output(h5, GEOMETRY, RequestedOutput.COORDS)
    assert not verdict.valid
    assert verdict.reason is ReasonCode.MISSING_ATTRS


def test_geometry_mismatch(tmp_path: Path) -> None:
    h5 = write_patch_h5(tmp_path / "s.h5", patch_size=512)
    verdict = validate_output(h5, GEOMETRY, RequestedOutput.COORDS)
    assert not verdict.valid
    assert verdict.reason is ReasonCode.GEOMETRY_MISMATCH


def test_missing_features(tmp_path: Path) -> None:
    h5 = write_patch_h5(tmp_path / "s.h5")  # coords only, no features
    verdict = validate_output(h5, GEOMETRY, RequestedOutput.FEATURES, ENC)
    assert not verdict.valid
    assert verdict.reason is ReasonCode.MISSING_FEATURES


def test_row_mismatch(tmp_path: Path) -> None:
    h5 = write_patch_h5(tmp_path / "s.h5", n=8, encoders=ENC, feature_rows=5)
    verdict = validate_output(h5, GEOMETRY, RequestedOutput.FEATURES, ENC)
    assert not verdict.valid
    assert verdict.reason is ReasonCode.ROW_MISMATCH


def test_nan_features(tmp_path: Path) -> None:
    h5 = write_patch_h5(tmp_path / "s.h5", encoders=ENC, inject_nan=True)
    verdict = validate_output(h5, GEOMETRY, RequestedOutput.FEATURES, ENC)
    assert not verdict.valid
    assert verdict.reason is ReasonCode.NAN_FEATURES


def test_coords_valid_but_features_requested_still_checks_features(tmp_path: Path) -> None:
    # Same file is valid for coords but invalid for features — branch-on-output.
    h5 = write_patch_h5(tmp_path / "s.h5")
    assert validate_output(h5, GEOMETRY, RequestedOutput.COORDS).valid
    assert not validate_output(h5, GEOMETRY, RequestedOutput.FEATURES, ENC).valid


def test_predicate_is_pure_same_state_same_verdict(tmp_path: Path) -> None:
    h5 = write_patch_h5(tmp_path / "s.h5", encoders=ENC)
    first = validate_output(h5, GEOMETRY, RequestedOutput.FEATURES, ENC)
    second = validate_output(h5, GEOMETRY, RequestedOutput.FEATURES, ENC)
    assert first == second


@pytest.mark.parametrize("requested", [RequestedOutput.COORDS, RequestedOutput.FEATURES])
def test_valid_fixture_round_trips(tmp_path: Path, requested: RequestedOutput) -> None:
    encoders = ENC if requested is RequestedOutput.FEATURES else ()
    h5 = write_patch_h5(tmp_path / "s.h5", encoders=encoders)
    assert validate_output(h5, GEOMETRY, requested, encoders).valid
