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
default and needs no cloud credentials; the opt-in BigQuery backend (phase 4,
``atlas_conductor.telemetry_bigquery``) is added behind the same interface without
changing what any agent records. The phase-2 PHI-free write gate (design D12) wraps
this sink as a write-time filter — additive, because the records are already
metadata-only.

Phase 4 (``add-conductor-distribution``) adds a fifth family, ``message_flow``: one
metadata-only record per inter-agent interaction, emitted by both the in-process and the
A2A transport (design D-DIST-2/3), which the GUI Level-2 message-flow view renders.
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


@dataclass(frozen=True)
class MessageFlowRecord:
    """One row in ``message_flow``: a single inter-agent interaction (design D-DIST-3).

    Emitted by both the in-process and the A2A transport for each routed interaction, so
    the GUI Level-2 message-flow view renders from persisted telemetry rather than a live
    socket. All fields are operational metadata — agent identifiers, an enum message type,
    and a correlation id — with no array field, so the metadata-only invariant (design D9)
    holds by type. ``slide_stem`` flows through the same PHI-free gate as the other families.
    """

    job_id: str
    from_agent: str  # planner / worker / validator / recovery / scheduler
    to_agent: str
    message_type: str  # a MessageType value (declarative intent of the message)
    correlation_id: str
    slide_stem: str | None = None
    stage: str | None = None
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

    @abstractmethod
    def record_message_flow(self, record: MessageFlowRecord) -> None:
        ...

    def read_agent_events(self) -> list[dict[str, Any]]:
        """Read back the ``agent_events`` family as rows (for the decision trace)."""
        raise NotImplementedError

    def read_slide_stage_outcomes(self) -> list[dict[str, Any]]:
        """Read back the ``slide_stage_outcomes`` family as rows."""
        raise NotImplementedError

    def read_message_flow(self) -> list[dict[str, Any]]:
        """Read back the ``message_flow`` family as rows (for the Level-2 view)."""
        raise NotImplementedError


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    for key, value in row.items():
        if isinstance(value, Enum):
            row[key] = value.value
        elif isinstance(value, Path):
            row[key] = str(value)
    return row


def _record_to_dict(record: Any) -> dict[str, Any]:
    """Serialize a typed record to a JSON-safe dict without stamping."""
    if not is_dataclass(record):  # defensive: only typed records are accepted
        raise TypeError(f"telemetry only accepts typed records, got {type(record).__name__}")
    return _normalize_row(asdict(record))


def _to_row(record: Any) -> dict[str, Any]:
    """Serialize a record to a JSON-safe dict, stamping a timestamp if absent."""
    row = _record_to_dict(record)
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
        "message_flow": "message_flow.jsonl",
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

    def record_message_flow(self, record: MessageFlowRecord) -> None:
        self._append("message_flow", record)

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

    def read_agent_events(self) -> list[dict[str, Any]]:
        return self.read_family("agent_events")

    def read_slide_stage_outcomes(self) -> list[dict[str, Any]]:
        return self.read_family("slide_stage_outcomes")

    def read_message_flow(self) -> list[dict[str, Any]]:
        return self.read_family("message_flow")


class InMemoryTelemetrySink(TelemetrySink):
    """A backend that keeps records in lists — convenient for tests and assertions."""

    def __init__(self) -> None:
        self.jobs: list[JobRecord] = []
        self.slide_stage_outcomes: list[SlideStageOutcomeRecord] = []
        self.validation_results: list[ValidationResultRecord] = []
        self.agent_events: list[AgentEventRecord] = []
        self.message_flow: list[MessageFlowRecord] = []

    def record_job(self, record: JobRecord) -> None:
        self.jobs.append(record)

    def record_slide_stage_outcome(self, record: SlideStageOutcomeRecord) -> None:
        self.slide_stage_outcomes.append(record)

    def record_validation(self, record: ValidationResultRecord) -> None:
        self.validation_results.append(record)

    def record_agent_event(self, record: AgentEventRecord) -> None:
        self.agent_events.append(record)

    def record_message_flow(self, record: MessageFlowRecord) -> None:
        self.message_flow.append(record)

    def read_agent_events(self) -> list[dict[str, Any]]:
        return [_record_to_dict(r) for r in self.agent_events]

    def read_slide_stage_outcomes(self) -> list[dict[str, Any]]:
        return [_record_to_dict(r) for r in self.slide_stage_outcomes]

    def read_message_flow(self) -> list[dict[str, Any]]:
        return [_record_to_dict(r) for r in self.message_flow]
