"""Tests for the YAML job-config loader/validator (task 2.4).

Covers the orchestration-run 'Job config intake' scenarios: a valid config is
accepted, a missing required field is rejected naming the field, and an unsupported
requested output is rejected stating what is supported.
"""

from __future__ import annotations

import pytest

from atlas_conductor.config import JobConfigError, parse_job_config
from atlas_conductor.contracts import Command, RequestedOutput


def _valid_features_config() -> dict:
    return {
        "input_dir": "/data/cohort",
        "output_dir": "/data/out",
        "requested_output": "features",
        "patch_size": 256,
        "target_mag": 20,
        "encoders": ["resnet50"],
    }


def test_valid_features_config() -> None:
    config = parse_job_config(_valid_features_config())
    assert config.requested_output is RequestedOutput.FEATURES
    assert config.geometry.patch_size == 256
    assert config.encoders == ("resnet50",)
    assert config.command is Command.PROCESS


def test_valid_coords_config_needs_no_encoder() -> None:
    raw = {
        "input_dir": "/data/cohort",
        "output_dir": "/data/out",
        "requested_output": "coords",
        "patch_size": 256,
        "target_mag": 20,
    }
    config = parse_job_config(raw)
    assert config.command is Command.SEGMENT_AND_GET_COORDS


def test_missing_patch_size_names_field() -> None:
    raw = _valid_features_config()
    del raw["patch_size"]
    with pytest.raises(JobConfigError, match="patch_size"):
        parse_job_config(raw)


def test_hyphenated_keys_accepted() -> None:
    raw = {
        "input-dir": "/data/cohort",
        "output-dir": "/data/out",
        "requested-output": "coords",
        "patch-size": 256,
        "target-mag": 20,
    }
    config = parse_job_config(raw)
    assert config.geometry.patch_size == 256


def test_unsupported_requested_output_rejected() -> None:
    raw = _valid_features_config()
    raw["requested_output"] = "slide-embeddings"
    with pytest.raises(JobConfigError, match="supported outputs"):
        parse_job_config(raw)


def test_features_without_encoder_rejected() -> None:
    raw = _valid_features_config()
    del raw["encoders"]
    with pytest.raises(JobConfigError, match="encoder"):
        parse_job_config(raw)
