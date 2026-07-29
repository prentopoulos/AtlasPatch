"""Append-only, typed, metadata-only telemetry (tasks 7.1, 7.2).

Four record families — ``jobs``, ``slide_stage_outcomes``, ``validation_results``,
``agent_events`` — are enough to reconstruct a run after the fact (run-telemetry
spec). The metadata-only invariant (design D9) is enforced *by type*: every record is
a frozen dataclass of scalars, enums, timestamps, and identifiers, with no field able
to hold a WSI image, a tissue mask, or an embedding matrix. There is deliberately no
sink method that accepts an array — pixels and embeddings can only ever live in the
AtlasPatch HDF5 on disk.

The ``slide_stage_outcomes`` records carry the labeled recovery fields
``(signature, classification, action, resolved)`` plus the fake adapter's
``injected_label`` ground truth (design D14), so a run's telemetry doubles as a
labeled dataset of recovery attempts.

The sink is one pluggable interface (design D9): the local JSONL backend is the
default and needs no cloud credentials; a BigQuery backend is added in phase 4 behind
the same interface without changing what any agent records. The phase-2 PHI-free
write gate (design D12) will wrap this sink as a write-time filter — additive,
because the records are already metadata-only.
"""

from __future__ import annotations

import json
import threading
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class JobRecord:
    """One row in the ``jobs`` family: a run's lifecycle and cohort tallies."""

    job_id: str
    input_dir: str
    requested_output: str
    patch_size: int
    target_mag: int
    encoders: str  # comma-joined; never an array
    adapter: str
    status: str
    cohort_size: int = 0
    valid_count: int = 0
    skipped_count: int = 0
    quarantined_count: int = 0
    blocked_count: int = 0
    started_at: str = ""
    finished_at: str = ""


@dataclass(frozen=True)
class SlideStageOutcomeRecord:
    """One row in ``slide_stage_outcomes``: a slide's outcome at one stage/attempt.

    Carries the labeled recovery tuple so the family is a recovery dataset (design D14).
    """

    job_id: str
    slide_stem: str
    stage: str
    command: str
    attempt: int
    outcome: str  # SlideOutcome value
    reason_code: str
    exit_code: int | None = None
    duration_s: float = 0.0
    signature: str | None = None  # failure signature (stderr class), A3
    classification: str | None = None  # recovery classification, A3
    action: str | None = None  # recovery action taken, A3
    resolved: bool | None = None  # did the action resolve the failure, A3
    injected_label: str | None = None  # fake-adapter ground truth, A3
    timestamp: str = ""


@dataclass(frozen=True)
class ValidationResultRecord:
    """One row in ``validation_results``: a structural verdict for a slide."""

    job_id: str
    slide_stem: str
    stage: str
    requested_output: str
    valid: bool
    reason_code: str
    detail: str = ""
    timestamp: str = ""


@dataclass(frozen=True)
class AgentEventRecord:
    """One row in ``agent_events``: an ordered decision by one logical agent.

    This family drives the decision trace (design D15) and the GUI Level 1
    component-state view (design D18). All fields are operational metadata.
    """

    job_id: str
    agent: str  # planner / worker / validator / recovery / scheduler
    event: str
    slide_stem: str | None = None
    stage: str | None = None
    reason_code: str | None = None
    detail: str = ""
    timestamp: str = ""


class TelemetrySink(ABC):
    """The append-only sink interface. Only typed records — no array method exists."""

    @abstractmethod
    def record_job(self, record: JobRecord) -> None:
        ...

    @abstractmethod
    def record_slide_stage_outcome(self, record: SlideStageOutcomeRecord) -> None:
        ...

    @abstractmethod
    def record_validation(self, record: ValidationResultRecord) -> None:
        ...

    @abstractmethod
    def record_agent_event(self, record: AgentEventRecord) -> None:
        ...


def _to_row(record: Any) -> dict[str, Any]:
    """Serialize a record to a JSON-safe dict, stamping a timestamp if absent."""
    if not is_dataclass(record):  # defensive: only typed records are accepted
        raise TypeError(f"telemetry only accepts typed records, got {type(record).__name__}")
    row = asdict(record)
    for key, value in row.items():
        if isinstance(value, Enum):
            row[key] = value.value
        elif isinstance(value, Path):
            row[key] = str(value)
    if "timestamp" in row and not row["timestamp"]:
        row["timestamp"] = _utcnow()
    return row


class JsonlTelemetrySink(TelemetrySink):
    """Local backend: one append-only ``<family>.jsonl`` file per record family."""

    _FILES = {
        "jobs": "jobs.jsonl",
        "slide_stage_outcomes": "slide_stage_outcomes.jsonl",
        "validation_results": "validation_results.jsonl",
        "agent_events": "agent_events.jsonl",
    }

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _append(self, family: str, record: Any) -> None:
        row = _to_row(record)
        line = json.dumps(row, sort_keys=True)
        path = self.directory / self._FILES[family]
        with self._lock, path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def record_job(self, record: JobRecord) -> None:
        self._append("jobs", record)

    def record_slide_stage_outcome(self, record: SlideStageOutcomeRecord) -> None:
        self._append("slide_stage_outcomes", record)

    def record_validation(self, record: ValidationResultRecord) -> None:
        self._append("validation_results", record)

    def record_agent_event(self, record: AgentEventRecord) -> None:
        self._append("agent_events", record)

    def read_family(self, family: str) -> list[dict[str, Any]]:
        """Read back a family as a list of rows (used by the report and tests)."""
        path = self.directory / self._FILES[family]
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows


class InMemoryTelemetrySink(TelemetrySink):
    """A backend that keeps records in lists — convenient for tests and assertions."""

    def __init__(self) -> None:
        self.jobs: list[JobRecord] = []
        self.slide_stage_outcomes: list[SlideStageOutcomeRecord] = []
        self.validation_results: list[ValidationResultRecord] = []
        self.agent_events: list[AgentEventRecord] = []

    def record_job(self, record: JobRecord) -> None:
        self.jobs.append(record)

    def record_slide_stage_outcome(self, record: SlideStageOutcomeRecord) -> None:
        self.slide_stage_outcomes.append(record)

    def record_validation(self, record: ValidationResultRecord) -> None:
        self.validation_results.append(record)

    def record_agent_event(self, record: AgentEventRecord) -> None:
        self.agent_events.append(record)
