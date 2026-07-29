"""YAML job-config schema, loader, and validator (task 2.4).

The job config is the single declarative input to a run: which cohort directory,
which output, which geometry, which encoders. Validation happens here, before any
plan is built or work dispatched (orchestration-run spec: "reject … before any work
is dispatched").

``pyyaml`` is an orchestrator-extra dependency; import it lazily so importing this
module never fails for a core-only install, and raise an actionable error only if a
config is actually loaded without the extra present.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atlas_conductor.contracts import (
    COMMAND_FOR_OUTPUT,
    Command,
    Geometry,
    RequestedOutput,
    Tuning,
)

# The MVP command set (design non-goals: only these two commands).
MVP_COMMANDS: frozenset[Command] = frozenset({Command.SEGMENT_AND_GET_COORDS, Command.PROCESS})

_REQUIRED_ALWAYS = ("input_dir", "output_dir", "requested_output", "patch_size", "target_mag")


class JobConfigError(ValueError):
    """A job config is missing a field, malformed, or requests unsupported output."""


@dataclass(frozen=True)
class JobConfig:
    """A validated job config."""

    input_dir: Path
    output_dir: Path
    requested_output: RequestedOutput
    geometry: Geometry
    encoders: tuple[str, ...] = ()
    unattended: bool = False
    attempt_budget: int = 3
    tuning: Tuning = Tuning()

    @property
    def command(self) -> Command:
        return COMMAND_FOR_OUTPUT[self.requested_output]


def _normalize_keys(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept both ``patch-size`` and ``patch_size`` spellings from YAML."""
    return {str(k).strip().replace("-", "_"): v for k, v in raw.items()}


def load_job_config(path: str | Path) -> JobConfig:
    """Read and validate a YAML job config from ``path``."""
    config_path = Path(path)
    if not config_path.is_file():
        raise JobConfigError(f"job config not found: {config_path}")
    try:
        import yaml  # type: ignore[import-untyped]
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised only without the extra
        raise JobConfigError(
            "reading a YAML job config requires PyYAML; install the orchestrator extra: "
            "pip install 'atlas-patch[orchestrator]'"
        ) from exc
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise JobConfigError(f"job config must be a YAML mapping, got {type(raw).__name__}")
    return parse_job_config(raw)


def parse_job_config(raw: dict[str, Any]) -> JobConfig:
    """Validate an already-parsed config mapping into a :class:`JobConfig`."""
    data = _normalize_keys(raw)

    missing = [key for key in _REQUIRED_ALWAYS if data.get(key) in (None, "")]
    if missing:
        raise JobConfigError(
            "job config is missing required field(s): " + ", ".join(sorted(missing))
        )

    output_value = str(data["requested_output"]).strip().lower()
    try:
        requested_output = RequestedOutput(output_value)
    except ValueError as exc:
        supported = ", ".join(o.value for o in RequestedOutput)
        raise JobConfigError(
            f"unsupported requested_output {output_value!r}; supported outputs: {supported}"
        ) from exc

    command = COMMAND_FOR_OUTPUT[requested_output]
    if command not in MVP_COMMANDS:
        supported = ", ".join(c.value for c in MVP_COMMANDS)
        raise JobConfigError(
            f"requested_output {output_value!r} maps to command {command.value!r}, "
            f"which is outside the MVP set; supported commands: {supported}"
        )

    encoders = _parse_encoders(data.get("encoders"))
    if requested_output is RequestedOutput.FEATURES and not encoders:
        raise JobConfigError(
            "requested_output 'features' requires at least one encoder in 'encoders'"
        )

    geometry = Geometry(
        patch_size=_as_int(data["patch_size"], field="patch_size"),
        target_mag=_as_int(data["target_mag"], field="target_mag"),
        step_size=(
            _as_int(data["step_size"], field="step_size")
            if data.get("step_size") not in (None, "")
            else None
        ),
    )

    return JobConfig(
        input_dir=Path(str(data["input_dir"])).expanduser(),
        output_dir=Path(str(data["output_dir"])).expanduser(),
        requested_output=requested_output,
        geometry=geometry,
        encoders=encoders,
        unattended=bool(data.get("unattended", False)),
        attempt_budget=_as_int(data.get("attempt_budget", 3), field="attempt_budget"),
    )


def _parse_encoders(value: Any) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list | tuple):
        items = list(value)
    else:
        raise JobConfigError(f"'encoders' must be a string or list, got {type(value).__name__}")
    return tuple(str(item).strip().lower() for item in items if str(item).strip())


def _as_int(value: Any, *, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise JobConfigError(f"'{field}' must be an integer, got {value!r}") from exc
