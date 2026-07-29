"""Tests for the telemetry sink and its metadata-only-by-type invariant (task 7.1).

Asserts structurally that no telemetry record family has a field able to hold an
array/image/embedding, and that the sink exposes no method accepting one — the
metadata-only invariant is enforced by type, not by discipline (design D9).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from atlas_conductor import telemetry as t

_RECORD_TYPES = (
    t.JobRecord,
    t.SlideStageOutcomeRecord,
    t.ValidationResultRecord,
    t.AgentEventRecord,
)

_SCALAR_TYPES = {"int", "float", "str", "bool"}


def _leaf_type_names(annotation: object) -> set[str]:
    text = str(annotation)
    names: set[str] = set()
    for token in text.replace("|", " ").replace("[", " ").replace("]", " ").split():
        token = token.strip(", ")
        if token:
            names.add(token.split(".")[-1])
    return names


def test_no_record_type_has_an_array_field() -> None:
    for record_type in _RECORD_TYPES:
        for field in dataclasses.fields(record_type):
            names = _leaf_type_names(field.type)
            forbidden = {"ndarray", "list", "tuple", "dict", "bytes", "Image", "array"}
            assert not (
                names & forbidden
            ), f"{record_type.__name__}.{field.name} has a non-scalar type {field.type!r}"
            allowed = _SCALAR_TYPES | {"None", "Optional", "NoneType"}
            assert (
                names <= allowed
            ), f"{record_type.__name__}.{field.name} type {field.type!r} is not scalar-only"


def test_sink_has_no_array_accepting_method() -> None:
    # Every public record_* method takes exactly one typed-record argument.
    methods = [m for m in dir(t.TelemetrySink) if m.startswith("record_")]
    assert set(methods) == {
        "record_job",
        "record_slide_stage_outcome",
        "record_validation",
        "record_agent_event",
    }


def test_jsonl_backend_is_append_only(tmp_path: Path) -> None:
    sink = t.JsonlTelemetrySink(tmp_path)
    sink.record_agent_event(t.AgentEventRecord(job_id="j", agent="planner", event="a"))
    sink.record_agent_event(t.AgentEventRecord(job_id="j", agent="planner", event="b"))
    rows = sink.read_family("agent_events")
    assert [r["event"] for r in rows] == ["a", "b"]
    assert all(r["timestamp"] for r in rows)  # timestamp stamped on write
