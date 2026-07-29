"""The opt-in BigQuery telemetry backend (run-telemetry spec, design D-DIST-4).

:class:`BigQueryTelemetrySink` implements the same append-only
:class:`~atlas_conductor.telemetry.TelemetrySink` interface as the default JSONL backend,
mapping each of the five record families to a table and each typed record to a row insert.
It changes nothing about *what* any agent records — the same typed records flow through the
same interface — so switching to it is purely an operational choice (a cohort-scale,
queryable backend) with no effect on the run.

The backend is **opt-in**: it is selected only when a job config sets ``telemetry.backend:
bigquery`` with a dataset, and ``google-cloud-bigquery`` is imported **behind a guard**
inside ``__init__`` — never at module import — so the core ``atlaspatch`` CLI import graph
stays cloud-free (design D-DIST-5). A client may be injected (the CI test passes a fake one),
so the row-shape contract is verifiable without a live GCP connection or the SDK installed.

Row-shape guarantee: rows are serialized with the same :func:`~atlas_conductor.telemetry._to_row`
the JSONL backend uses, so a family's BigQuery row equals its JSONL row by construction — the
"same records through the same interface" requirement is met, not merely intended.
"""

from __future__ import annotations

from typing import Any

from atlas_conductor.telemetry import (
    AgentEventRecord,
    JobRecord,
    MessageFlowRecord,
    SlideStageOutcomeRecord,
    TelemetrySink,
    ValidationResultRecord,
    _to_row,
)

# Each record family maps to a same-named table in the configured dataset.
FAMILY_TABLES: dict[str, str] = {
    "jobs": "jobs",
    "slide_stage_outcomes": "slide_stage_outcomes",
    "validation_results": "validation_results",
    "agent_events": "agent_events",
    "message_flow": "message_flow",
}


class BigQueryTelemetrySink(TelemetrySink):
    """Append telemetry to BigQuery through the standard sink interface (design D-DIST-4)."""

    def __init__(self, dataset: str, client: Any | None = None, project: str | None = None) -> None:
        """Open (or accept) a BigQuery client for ``dataset``.

        ``dataset`` is the BigQuery dataset id holding the family tables. ``client`` may be
        injected (used by tests to capture inserts); when omitted, ``google-cloud-bigquery``
        is imported and a real client is created — the only place the cloud SDK is touched.
        """
        if client is None:
            from google.cloud import bigquery  # guarded: imported only for a real client

            client = bigquery.Client(project=project)
        self._client = client
        self._dataset = dataset

    def _insert(self, family: str, record: Any) -> None:
        row = _to_row(record)  # same serialization as the JSONL backend → identical rows
        table_id = f"{self._dataset}.{FAMILY_TABLES[family]}"
        errors = self._client.insert_rows_json(table_id, [row])
        if errors:  # BigQuery returns a non-empty list of per-row errors on failure
            raise RuntimeError(f"BigQuery insert into {table_id} failed: {errors}")

    def record_job(self, record: JobRecord) -> None:
        self._insert("jobs", record)

    def record_slide_stage_outcome(self, record: SlideStageOutcomeRecord) -> None:
        self._insert("slide_stage_outcomes", record)

    def record_validation(self, record: ValidationResultRecord) -> None:
        self._insert("validation_results", record)

    def record_agent_event(self, record: AgentEventRecord) -> None:
        self._insert("agent_events", record)

    def record_message_flow(self, record: MessageFlowRecord) -> None:
        self._insert("message_flow", record)
