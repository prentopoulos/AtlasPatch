"""Tests for the PHI-free write-gate and egress containment (tasks 1.4, 2.1, 2.2).

Covers the ``phi-safe-telemetry`` capability: slide stems are pseudonymized before
persistence (a stem that is itself an identifier is neutralized, not stored raw), an
unneutralizable Safe-Harbor identifier in a free-text field is rejected fail-closed, no
telemetry/audit record field can carry an array, and a core run opens no unexpected
network connection (design D12/D19/D20/D23).
"""

from __future__ import annotations

import dataclasses
import socket
from pathlib import Path

from atlas_conductor import telemetry as t
from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import Geometry, RequestedOutput, SlideOutcome
from atlas_conductor.dispatch import FakeAdapter
from atlas_conductor.governance.audit import AuditEntry, InMemoryAuditTrail
from atlas_conductor.governance.gate import PhiSafeSink
from atlas_conductor.governance.phi import (
    is_pseudonym,
    pseudonymize_stem,
    safe_harbor_findings,
)
from atlas_conductor.run import run_job
from atlas_conductor.telemetry import (
    AgentEventRecord,
    InMemoryTelemetrySink,
    SlideStageOutcomeRecord,
)

GEO = Geometry(patch_size=256, target_mag=20)


# -- pseudonymization (task 1.4) -------------------------------------------------


def test_pseudonym_is_stable_within_a_run_and_unlinkable_across_runs() -> None:
    # Stable within a run (same job_id) → records stay correlatable.
    assert pseudonymize_stem("mrn-00123", "job-1") == pseudonymize_stem("mrn-00123", "job-1")
    # Different job_id → different pseudonym → cross-run comparison cannot recover identity.
    assert pseudonymize_stem("mrn-00123", "job-1") != pseudonymize_stem("mrn-00123", "job-2")
    # The token is non-identifying and never contains the raw stem.
    token = pseudonymize_stem("mrn-00123", "job-1")
    assert is_pseudonym(token)
    assert "mrn-00123" not in token


def test_mrn_shaped_stem_is_pseudonymized_not_rejected() -> None:
    sink = InMemoryTelemetrySink()
    audit = InMemoryAuditTrail()
    gate = PhiSafeSink(sink, audit=audit)

    # A stem that is itself an accession/MRN — must be neutralized, never stored raw.
    gate.record_slide_stage_outcome(
        SlideStageOutcomeRecord(
            job_id="j",
            slide_stem="123456789",
            stage="segment",
            command="segment-and-get-coords",
            attempt=1,
            outcome="valid",
            reason_code="valid",
        )
    )
    assert len(sink.slide_stage_outcomes) == 1  # passed through (not rejected)
    persisted = sink.slide_stage_outcomes[0].slide_stem
    assert persisted == pseudonymize_stem("123456789", "j")
    assert persisted != "123456789"  # raw identifier never lands
    assert audit.entries() == []  # nothing rejected


def test_identifier_in_detail_field_is_rejected_fail_closed() -> None:
    sink = InMemoryTelemetrySink()
    audit = InMemoryAuditTrail()
    gate = PhiSafeSink(sink, audit=audit)

    # A leaked SSN in a free-text detail field cannot be neutralized → reject.
    gate.record_agent_event(
        AgentEventRecord(
            job_id="j",
            agent="recovery",
            event="recover",
            slide_stem="s",
            detail="crash; patient ssn 123-45-6789 in stderr tail",
        )
    )
    assert sink.agent_events == []  # dropped, not persisted
    entries = audit.entries()
    assert len(entries) == 1
    assert entries[0]["action"] == "phi-gate-rejection"
    assert "ssn" in entries[0]["payload"]["shapes"]
    # The rejection records the *shape*, never the matched identifier value.
    assert "123-45-6789" not in str(entries[0]["payload"])


def test_benign_record_passes_through_with_only_its_stem_changed() -> None:
    sink = InMemoryTelemetrySink()
    gate = PhiSafeSink(sink, audit=InMemoryAuditTrail())
    gate.record_agent_event(
        AgentEventRecord(
            job_id="j",
            agent="worker",
            event="dispatch",
            slide_stem="slideA",
            stage="embed",
            detail="reduce batch (rung 1)",
        )
    )
    rec = sink.agent_events[0]
    assert rec.slide_stem == pseudonymize_stem("slideA", "j")  # stem changed
    assert rec.agent == "worker" and rec.event == "dispatch" and rec.stage == "embed"
    assert rec.detail == "reduce batch (rung 1)"  # benign detail passes through intact


def test_phi_laden_stem_injected_via_run_never_reaches_the_store(tmp_path: Path) -> None:
    # End-to-end (CI proof): a cohort whose file stem is an identifier is pseudonymized,
    # so the raw identifier is provable-absent from the telemetry store after the run.
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    (cohort / "987654321.svs").write_bytes(b"fake-wsi")
    config = JobConfig(
        input_dir=cohort,
        output_dir=tmp_path / "out",
        requested_output=RequestedOutput.COORDS,
        geometry=GEO,
    )
    sink = InMemoryTelemetrySink()
    result = run_job(config, sink, adapter=FakeAdapter())

    assert result.count(SlideOutcome.VALID) == 1
    persisted_blob = " ".join(
        str(r) for r in (*sink.slide_stage_outcomes, *sink.agent_events, *sink.validation_results)
    )
    assert "987654321" not in persisted_blob  # raw identifier never persisted


# -- egress containment (tasks 2.1, 2.2) -----------------------------------------


def test_no_telemetry_or_audit_field_can_hold_an_array() -> None:
    record_types = (
        t.JobRecord,
        t.SlideStageOutcomeRecord,
        t.ValidationResultRecord,
        t.AgentEventRecord,
        AuditEntry,
    )
    forbidden = {"ndarray", "bytes", "Image", "array"}
    for record_type in record_types:
        for field in dataclasses.fields(record_type):
            names = {
                tok.split(".")[-1]
                for tok in str(field.type)
                .replace("|", " ")
                .replace("[", " ")
                .replace("]", " ")
                .split()
            }
            assert not (names & forbidden), f"{record_type.__name__}.{field.name} is array-capable"


def test_audit_payload_rejects_a_non_scalar_value() -> None:
    # The no-array guarantee for the audit trail is enforced by construction.
    audit = InMemoryAuditTrail()
    try:
        audit.append("x", {"pixels": [1, 2, 3]})
    except TypeError as exc:
        assert "scalar" in str(exc)
    else:  # pragma: no cover - the append must raise
        raise AssertionError("audit trail accepted a non-scalar payload value")


def test_core_run_opens_no_unexpected_network_connection(tmp_path: Path, monkeypatch) -> None:
    attempted: list[object] = []

    def _forbid_connect(self: socket.socket, address: object) -> None:
        attempted.append(address)
        raise AssertionError(f"unexpected network connection to {address!r}")

    monkeypatch.setattr(socket.socket, "connect", _forbid_connect)

    cohort = tmp_path / "cohort"
    cohort.mkdir()
    for stem in ["a", "b"]:
        (cohort / f"{stem}.svs").write_bytes(b"fake-wsi")
    config = JobConfig(
        input_dir=cohort,
        output_dir=tmp_path / "out",
        requested_output=RequestedOutput.FEATURES,
        geometry=GEO,
        encoders=("resnet50",),
    )
    result = run_job(config, InMemoryTelemetrySink(), adapter=FakeAdapter())

    assert result.count(SlideOutcome.VALID) == 2
    assert attempted == []  # the core path made no outbound connection


def test_safe_harbor_findings_names_shapes_without_false_positives_on_operational_text() -> None:
    # Ordinary operational text never trips the matcher.
    assert safe_harbor_findings("reduce batch (rung 2) patch_size=256 attempt=3") == []
    assert safe_harbor_findings("cohort=12 output=features nodes=6") == []
    # Real identifier shapes are named.
    assert "email" in safe_harbor_findings("contact jane@hospital.org")
    assert "date" in safe_harbor_findings("collected 2024-03-05")
    assert "long-digit-run" in safe_harbor_findings("accession 000123456")
