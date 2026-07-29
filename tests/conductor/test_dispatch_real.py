"""Tests for the real adapter's argv construction (task 5.2).

The real adapter runs a GPU subprocess and is kept out of the CI happy path, but its
argv builder is a pure function and is tested here — no subprocess is spawned.
"""

from __future__ import annotations

from pathlib import Path

from atlas_conductor.contracts import (
    Command,
    Geometry,
    RequestedOutput,
    Stage,
    Task,
    TaskTarget,
    Tuning,
)
from atlas_conductor.dispatch import build_argv

BASE = ["atlaspatch"]


def _task(command: Command, output: RequestedOutput, tuning: Tuning | None = None) -> Task:
    return Task(
        stage=Stage.EMBED if output is RequestedOutput.FEATURES else Stage.SEGMENT,
        command=command,
        requested_output=output,
        input_path=Path("/data/cohort"),
        output_dir=Path("/data/out"),
        targets=(TaskTarget("s", Path("/data/cohort/s.svs"), Path("/data/out/patches/s.h5")),),
        geometry=Geometry(patch_size=256, target_mag=20, step_size=128),
        encoders=("resnet50",) if output is RequestedOutput.FEATURES else (),
        tuning=tuning or Tuning(),
    )


def test_process_argv_has_geometry_and_encoders() -> None:
    argv = build_argv(_task(Command.PROCESS, RequestedOutput.FEATURES), BASE)
    assert argv[:2] == ["atlaspatch", "process"]
    assert str(Path("/data/cohort")) in argv
    assert "--output" in argv and "--patch-size" in argv and "256" in argv
    assert "--target-mag" in argv and "20" in argv
    assert "--step-size" in argv and "128" in argv
    assert "--feature-extractors" in argv
    assert argv[argv.index("--feature-extractors") + 1] == "resnet50"


def test_coords_argv_omits_feature_flags() -> None:
    argv = build_argv(_task(Command.SEGMENT_AND_GET_COORDS, RequestedOutput.COORDS), BASE)
    assert argv[:2] == ["atlaspatch", "segment-and-get-coords"]
    assert "--feature-extractors" not in argv
    assert "--feature-batch-size" not in argv


def test_tuning_and_force_flags() -> None:
    tuning = Tuning(feature_batch_size=8, seg_batch_size=1, patch_workers=2, force=True)
    argv = build_argv(_task(Command.PROCESS, RequestedOutput.FEATURES, tuning), BASE)
    assert argv[argv.index("--feature-batch-size") + 1] == "8"
    assert argv[argv.index("--seg-batch-size") + 1] == "1"
    assert argv[argv.index("--patch-workers") + 1] == "2"
    assert "--force" in argv


def test_no_force_when_not_requested() -> None:
    argv = build_argv(_task(Command.PROCESS, RequestedOutput.FEATURES), BASE)
    assert "--force" not in argv


def test_multiple_encoders_comma_joined() -> None:
    task = _task(Command.PROCESS, RequestedOutput.FEATURES)
    task = Task(**{**task.__dict__, "encoders": ("resnet50", "uni")})
    argv = build_argv(task, BASE)
    assert argv[argv.index("--feature-extractors") + 1] == "resnet50,uni"
