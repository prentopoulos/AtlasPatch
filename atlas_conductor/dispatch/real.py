"""The real execution adapter (task 5.2).

The real adapter is the production counterpart of the fake adapter behind the same
:class:`~atlas_conductor.dispatch.base.ExecutionAdapter` interface. It translates a
declarative :class:`~atlas_conductor.contracts.Task` into an AtlasPatch CLI invocation,
runs it as a subprocess, and captures the raw outcome (exit code, stdout/stderr tails,
timing, produced paths). It builds argv from the task's declarative fields alone
(design D10) — the task never carries a pre-baked command line.

This adapter drives real GPU work, so it is deliberately kept out of the CI happy path
(the fake adapter covers CI). ``build_argv`` is factored out as a pure function so the
argv construction is unit-tested without spawning a subprocess.
"""

from __future__ import annotations

import subprocess
import sys
import time

from atlas_conductor.contracts import Command, Outcome, Task
from atlas_conductor.dispatch.base import ExecutionAdapter

# How many characters of each stream to retain for classification/triage. The tails are
# operational metadata (short text), never pixels or embeddings.
_TAIL_CHARS = 4000


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def build_argv(task: Task, base_cmd: list[str] | None = None) -> list[str]:
    """Construct the AtlasPatch CLI argv for ``task`` from its declarative fields.

    Pure and side-effect free. ``base_cmd`` defaults to invoking the installed
    AtlasPatch CLI module with the current interpreter.
    """
    argv = list(base_cmd) if base_cmd is not None else [sys.executable, "-m", "atlas_patch.cli"]
    argv.append(task.command.value)
    argv.append(str(task.input_path))
    argv += ["--output", str(task.output_dir)]
    argv += ["--patch-size", str(task.geometry.patch_size)]
    argv += ["--target-mag", str(task.geometry.target_mag)]
    if task.geometry.step_size is not None:
        argv += ["--step-size", str(task.geometry.step_size)]

    tuning = task.tuning
    if task.command is Command.PROCESS and task.encoders:
        argv += ["--feature-extractors", ",".join(task.encoders)]
        if tuning.feature_batch_size is not None:
            argv += ["--feature-batch-size", str(tuning.feature_batch_size)]
        if tuning.feature_precision is not None:
            argv += ["--feature-precision", str(tuning.feature_precision)]
    if tuning.seg_batch_size is not None:
        argv += ["--seg-batch-size", str(tuning.seg_batch_size)]
    if tuning.patch_workers is not None:
        argv += ["--patch-workers", str(tuning.patch_workers)]
    if tuning.max_open_slides is not None:
        argv += ["--max-open-slides", str(tuning.max_open_slides)]
    if tuning.force:
        argv.append("--force")
    # --verbose surfaces AtlasPatch's per-slide [FAIL] lines on stderr, which the
    # recovery agent parses as a classification hint (design D3).
    argv.append("--verbose")
    return argv


class RealAdapter(ExecutionAdapter):
    """Run AtlasPatch as a subprocess and return its raw outcome."""

    def __init__(self, base_cmd: list[str] | None = None, timeout_s: float | None = None) -> None:
        self._base_cmd = base_cmd
        self._timeout_s = timeout_s

    def execute(self, task: Task) -> Outcome:
        argv = build_argv(task, self._base_cmd)
        start = time.perf_counter()
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
                check=False,
            )
            exit_code = proc.returncode
            stdout, stderr = proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            exit_code = 124  # conventional timeout code
            stdout = _as_text(exc.stdout)
            stderr = _as_text(exc.stderr) + "\n[atlas_conductor] subprocess timed out"
        duration = time.perf_counter() - start

        produced = tuple(t.expected_h5_path for t in task.targets if t.expected_h5_path.exists())
        return Outcome(
            exit_code=exit_code,
            stdout_tail=stdout[-_TAIL_CHARS:],
            stderr_tail=stderr[-_TAIL_CHARS:],
            duration_s=duration,
            produced_paths=produced,
        )
