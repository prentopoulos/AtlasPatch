"""The fake execution adapter (task 5.3 — valid-output path, slice A1).

The fake adapter writes *structurally real* HDF5 files to each target's expected path
(design D5), so the validator's code path is identical for the fake and real adapters —
the structural checks are genuinely exercised in CI, not stubbed. It needs no GPU and
no real slides, so the whole plan → dispatch → validate → report loop runs in CI.

Slice A1 implements the valid-output path only. Slice A3 extends this adapter with
injectable execution failures (CUDA-OOM signature, precondition block) and injectable
structural-invalid outputs (row mismatch, NaNs, unopenable file), each carrying a
ground-truth ``injected_label`` so recovery can be tested against known truth.
"""

from __future__ import annotations

import time
from pathlib import Path

import h5py
import numpy as np

from atlas_conductor.contracts import Outcome, RequestedOutput, Task, TaskTarget
from atlas_conductor.dispatch.base import ExecutionAdapter
from atlas_conductor.validation import feature_dataset_key


class FakeAdapter(ExecutionAdapter):
    """Write canned-but-real HDF5 outputs for a task's targets."""

    def __init__(self, num_patches: int = 8, feature_dim: int = 16, seed: int = 0) -> None:
        self.num_patches = num_patches
        self.feature_dim = feature_dim
        self._rng = np.random.default_rng(seed)

    def execute(self, task: Task) -> Outcome:
        start = time.perf_counter()
        produced: list[Path] = []
        for target in task.targets:
            self._write_valid_output(task, target)
            produced.append(target.expected_h5_path)
        duration = time.perf_counter() - start
        return Outcome(
            exit_code=0,
            stdout_tail=f"[fake] wrote {len(produced)} output(s)",
            duration_s=duration,
            produced_paths=tuple(produced),
        )

    def _write_valid_output(self, task: Task, target: TaskTarget) -> None:
        path = target.expected_h5_path
        path.parent.mkdir(parents=True, exist_ok=True)
        n = self.num_patches
        coords = self._rng.integers(0, 10_000, size=(n, 5), dtype=np.int64)
        with h5py.File(path, "w") as handle:
            coords_ds = handle.create_dataset("coords", data=coords)
            # Required integer attrs, matching the job's requested geometry so the
            # validator's geometry check passes.
            for attr, value in (
                ("patch_size", task.geometry.patch_size),
                ("patch_size_level0", task.geometry.patch_size),
                ("target_magnification", task.geometry.target_mag),
            ):
                handle.attrs[attr] = int(value)
                coords_ds.attrs[attr] = int(value)
            handle.attrs["num_patches"] = int(n)
            if task.requested_output is RequestedOutput.FEATURES:
                features_grp = handle.create_group("features")
                for encoder in task.encoders:
                    key = feature_dataset_key(encoder).split("/", 1)[1]
                    features = self._rng.standard_normal((n, self.feature_dim)).astype(np.float32)
                    features_grp.create_dataset(key, data=features)
