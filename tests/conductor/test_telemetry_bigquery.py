"""BigQuery telemetry backend tests (run-telemetry spec, task 4.3).

Verifies the opt-in BigQuery backend against a *fake* client — no live GCP connection and no
``google-cloud-bigquery`` install needed — asserting the "same records through the same
interface" contract (design D-DIST-4): the row inserted for each family equals the row the
JSONL backend serializes, modulo the stamped timestamp.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from atlas_conductor.config import JobConfigError, parse_job_config
from atlas_conductor.telemetry import (
    AgentEventRecord,
    JobRecord,
    JsonlTelemetrySink,
    MessageFlowRecord,
    SlideStageOutcomeRecord,
    ValidationResultRecord,
)
from atlas_conductor.telemetry_bigquery import FAMILY_TABLES, BigQueryTelemetrySink


class _FakeBigQueryClient:
    """Captures ``insert_rows_json`` calls instead of talking to BigQuery."""

    def __init__(self) -> None:
        self.inserts: list[tuple[str, list[dict[str, Any]]]] = []

    def insert_rows_json(self, table_id: str, rows: list[dict[str, Any]]) -> list[Any]:
        self.inserts.append((table_id, rows))
        return []  # BigQuery returns an empty error list on success


def _one_of_each() -> list[tuple[str, Any]]:
    return [
        (
            "jobs",
            JobRecord(
                job_id="j",
                input_dir="in",
                requested_output="features",
                patch_size=256,
                target_mag=20,
                encoders="resnet50",
                adapter="fake",
                status="complete",
            ),
        ),
        (
            "slide_stage_outcomes",
            SlideStageOutcomeRecord(
                job_id="j",
                slide_stem="s",
                stage="embed",
                command="process",
                attempt=1,
                outcome="valid",
                reason_code="valid",
            ),
        ),
        (
            "validation_results",
            ValidationResultRecord(
                job_id="j",
                slide_stem="s",
                stage="embed",
                requested_output="features",
                valid=True,
                reason_code="valid",
            ),
        ),
        ("agent_events", AgentEventRecord(job_id="j", agent="planner", event="plan")),
        (
            "message_flow",
            MessageFlowRecord(
                job_id="j",
                from_agent="planner",
                to_agent="worker",
                message_type="dispatch",
                correlation_id="c1",
            ),
        ),
    ]


def test_bigquery_rows_match_jsonl_rows(tmp_path: Path) -> None:
    client = _FakeBigQueryClient()
    bq = BigQueryTelemetrySink("my_dataset", client=client)
    jsonl = JsonlTelemetrySink(tmp_path)

    record_by_family: dict[str, Callable[[Any], None]] = {
        "jobs": bq.record_job,
        "slide_stage_outcomes": bq.record_slide_stage_outcome,
        "validation_results": bq.record_validation,
        "agent_events": bq.record_agent_event,
        "message_flow": bq.record_message_flow,
    }
    jsonl_by_family: dict[str, Callable[[Any], None]] = {
        "jobs": jsonl.record_job,
        "slide_stage_outcomes": jsonl.record_slide_stage_outcome,
        "validation_results": jsonl.record_validation,
        "agent_events": jsonl.record_agent_event,
        "message_flow": jsonl.record_message_flow,
    }

    for family, record in _one_of_each():
        record_by_family[family](record)
        jsonl_by_family[family](record)

    # One insert per record, into the family's dataset-qualified table.
    assert len(client.inserts) == len(_one_of_each())
    for (table_id, rows), (family, _record) in zip(client.inserts, _one_of_each(), strict=True):
        assert table_id == f"my_dataset.{FAMILY_TABLES[family]}"
        (bq_row,) = rows
        (jsonl_row,) = (r for r in jsonl.read_family(family))  # same family, one record
        # Identical modulo the stamped timestamp (each backend stamps independently).
        bq_row.pop("timestamp", None)
        jsonl_row.pop("timestamp", None)
        assert bq_row == jsonl_row, family


def test_insert_failure_raises(tmp_path: Path) -> None:
    class _FailingClient:
        def insert_rows_json(self, table_id: str, rows: list[dict[str, Any]]) -> list[Any]:
            return [{"index": 0, "errors": ["boom"]}]

    bq = BigQueryTelemetrySink("ds", client=_FailingClient())
    try:
        bq.record_agent_event(AgentEventRecord(job_id="j", agent="planner", event="plan"))
    except RuntimeError as exc:
        assert "BigQuery insert" in str(exc)
    else:
        raise AssertionError("expected a RuntimeError on insert failure")


def test_config_selects_bigquery_backend_and_requires_dataset() -> None:
    base = {
        "input_dir": ".",
        "output_dir": "out",
        "requested_output": "coords",
        "patch_size": 256,
        "target_mag": 20,
    }
    default = parse_job_config(base)
    assert default.telemetry_backend == "jsonl"
    assert default.telemetry_dataset is None

    configured = parse_job_config({**base, "telemetry": {"backend": "bigquery", "dataset": "ds"}})
    assert configured.telemetry_backend == "bigquery"
    assert configured.telemetry_dataset == "ds"

    try:
        parse_job_config({**base, "telemetry": {"backend": "bigquery"}})
    except JobConfigError as exc:
        assert "dataset" in str(exc)
    else:
        raise AssertionError("bigquery backend without a dataset should be rejected")
