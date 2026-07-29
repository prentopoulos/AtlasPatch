"""A read-only reader over the JSONL telemetry families (design D18, D-GUI-1).

The GUI observes a run by *reading* the append-only telemetry, never by hooking the
orchestrator process or holding a live sink. This reader opens the per-family ``.jsonl``
files a :class:`~atlas_conductor.telemetry.JsonlTelemetrySink` writes and returns their rows
as plain dicts. It deliberately exposes **no** append/write method, so the read surface
cannot mutate telemetry, and it derives its filenames from the same mapping the sink
declares, so a family rename cannot silently desync the two.
"""

from __future__ import annotations

import json
from pathlib import Path

from atlas_conductor.telemetry import JsonlTelemetrySink

# The four telemetry families the observability surface renders over.
FAMILIES = ("jobs", "slide_stage_outcomes", "validation_results", "agent_events")


class TelemetryReader:
    """Read-only accessor for a directory of ``<family>.jsonl`` telemetry files.

    A missing directory or absent family file reads as an empty list, so the reader is
    safe to point at a sink that has not been written to yet (the GUI's empty state).
    """

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)

    def _read(self, family: str) -> list[dict]:
        # Reuse the sink's family→filename mapping so the reader can never drift from it.
        path = self.directory / JsonlTelemetrySink._FILES[family]
        if not path.exists():
            return []
        rows: list[dict] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def jobs(self) -> list[dict]:
        return self._read("jobs")

    def slide_stage_outcomes(self) -> list[dict]:
        return self._read("slide_stage_outcomes")

    def validation_results(self) -> list[dict]:
        return self._read("validation_results")

    def agent_events(self) -> list[dict]:
        return self._read("agent_events")

    def is_empty(self) -> bool:
        """True when no run has been recorded yet (drives the GUI empty state)."""
        return not any(self._read(family) for family in FAMILIES)
