"""The fake execution adapter (task 5.3).

The fake adapter writes *structurally real* HDF5 files to each target's expected path
(design D5), so the validator's code path is identical for the fake and real adapters.
It needs no GPU and no real slides, so the whole plan → dispatch → validate → recover
loop runs in CI.

Slice A1 delivered the valid-output path. Slice A3 adds **injectable failures** so
recovery is exercised against known ground truth (design D14): per-slide execution
failures (a CUDA-OOM stderr signature, a precondition block) and structural-invalid
outputs (NaN features, row-count mismatch, missing coords, unopenable file). Each
injection carries a ``label`` that flows into the outcome so CI can score the classifier
against truth. Injections are attempt-aware — ``fail_until_attempt`` lets a transient
failure resolve on a later retry — and the valid path honors skip-existing coord reuse,
so a re-embed after an OOM keeps the already-written segmentation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np

from atlas_conductor.contracts import Outcome, RequestedOutput, Task, TaskTarget
from atlas_conductor.dispatch.base import ExecutionAdapter
from atlas_conductor.validation import feature_dataset_key

# Injection modes and the stderr signature (if any) each surfaces.
_OOM_SIGNATURE = "RuntimeError: CUDA out of memory. Tried to allocate 2.00 GiB"
_PRECONDITION_SIGNATURE = "OSError: gated model requires a Hugging Face token (HF_TOKEN not set)"


@dataclass(frozen=True)
class Injection:
    """A per-slide injected failure for the fake adapter (design D5/D14)."""

    mode: str  # oom | precondition | nan | row_mismatch | no_coords | unopenable
    fail_until_attempt: int = 1_000_000  # fail attempts <= this; succeed afterwards
    label: str = ""


class FakeAdapter(ExecutionAdapter):
    """Write canned-but-real HDF5 outputs, optionally injecting labeled failures."""

    def __init__(
        self,
        num_patches: int = 8,
        feature_dim: int = 16,
        seed: int = 0,
        injections: dict[str, Injection] | None = None,
    ) -> None:
        self.num_patches = num_patches
        self.feature_dim = feature_dim
        self._rng = np.random.default_rng(seed)
        self._injections = injections or {}
        self._attempts: dict[str, int] = {}

    def execute(self, task: Task) -> Outcome:
        start = time.perf_counter()
        produced: list[Path] = []
        stderr_parts: list[str] = []
        label: str | None = None
        hard_exit = 0

        for target in task.targets:
            attempt = self._attempts.get(target.slide_stem, 0) + 1
            self._attempts[target.slide_stem] = attempt
            injection = self._active_injection(target.slide_stem, attempt)
            if injection is None:
                self._write_valid_output(task, target)
                produced.append(target.expected_h5_path)
            else:
                signature, exit_code = self._inject(task, target, injection)
                if signature:
                    stderr_parts.append(f"[FAIL] {target.slide_stem}: {signature}")
                if injection.label and label is None:
                    label = injection.label
                hard_exit = max(hard_exit, exit_code)
                if target.expected_h5_path.exists():
                    produced.append(target.expected_h5_path)

        duration = time.perf_counter() - start
        return Outcome(
            exit_code=hard_exit,
            stdout_tail=f"[fake] wrote {len(produced)} output(s)",
            stderr_tail="\n".join(stderr_parts),
            duration_s=duration,
            produced_paths=tuple(produced),
            injected_label=label,
        )

    def _active_injection(self, stem: str, attempt: int) -> Injection | None:
        injection = self._injections.get(stem)
        if injection is None or attempt > injection.fail_until_attempt:
            return None
        return injection

    def _inject(self, task: Task, target: TaskTarget, injection: Injection) -> tuple[str, int]:
        """Apply an injected failure. Returns ``(stderr_signature, exit_code)``."""
        path = target.expected_h5_path
        mode = injection.mode
        if mode == "oom":
            # Segmentation succeeded, feature extraction OOM'd: coords land, features do not.
            self._write_output(task, target, with_features=False)
            return _OOM_SIGNATURE, 0
        if mode == "precondition":
            return _PRECONDITION_SIGNATURE, 1  # gated encoder: nothing written
        if mode == "nan":
            self._write_output(task, target, with_features=True, nan=True)
            return "", 0
        if mode == "row_mismatch":
            self._write_output(task, target, with_features=True, feature_rows=self.num_patches - 3)
            return "", 0
        if mode == "no_coords":
            path.parent.mkdir(parents=True, exist_ok=True)
            with h5py.File(path, "w") as handle:
                handle.attrs["num_patches"] = 0
            return "", 0
        if mode == "unopenable":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"not an hdf5")
            return "", 0
        raise ValueError(f"unknown injection mode {mode!r}")

    def _write_valid_output(self, task: Task, target: TaskTarget) -> None:
        self._write_output(task, target, with_features=True)

    def _write_output(
        self,
        task: Task,
        target: TaskTarget,
        *,
        with_features: bool,
        nan: bool = False,
        feature_rows: int | None = None,
    ) -> None:
        path = target.expected_h5_path
        path.parent.mkdir(parents=True, exist_ok=True)
        want_features = with_features and task.requested_output is RequestedOutput.FEATURES

        # Honor skip-existing coord reuse (AtlasPatch semantics): if valid coords already
        # exist and this run is not forced, keep them and only (re)write features, so a
        # re-embed after an OOM preserves the already-written segmentation.
        reuse_coords = path.exists() and not task.tuning.force and _has_valid_coords(path)
        n = self._existing_patch_count(path) if reuse_coords else self.num_patches

        mode = "a" if reuse_coords else "w"
        with h5py.File(path, mode) as handle:
            if not reuse_coords:
                coords = self._rng.integers(0, 10_000, size=(n, 5), dtype=np.int64)
                coords_ds = handle.create_dataset("coords", data=coords)
                for attr, value in (
                    ("patch_size", task.geometry.patch_size),
                    ("patch_size_level0", task.geometry.patch_size),
                    ("target_magnification", task.geometry.target_mag),
                ):
                    handle.attrs[attr] = int(value)
                    coords_ds.attrs[attr] = int(value)
                handle.attrs["num_patches"] = int(n)
            if want_features:
                grp = handle.require_group("features")
                rows = feature_rows if feature_rows is not None else n
                for encoder in task.encoders:
                    key = feature_dataset_key(encoder).split("/", 1)[1]
                    if key in grp:
                        del grp[key]
                    features = self._rng.standard_normal((rows, self.feature_dim)).astype(
                        np.float32
                    )
                    if nan:
                        features[0, 0] = np.nan
                    grp.create_dataset(key, data=features)

    def _existing_patch_count(self, path: Path) -> int:
        with h5py.File(path, "r") as handle:
            return int(handle["coords"].shape[0])


def _has_valid_coords(path: Path) -> bool:
    try:
        with h5py.File(path, "r") as handle:
            coords = handle.get("coords")
            return isinstance(coords, h5py.Dataset) and coords.ndim == 2 and coords.shape[0] > 0
    except OSError:
        return False
