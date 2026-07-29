"""Tests for the tamper-evident audit trail (task 4.3).

Covers the ``audit-trail`` capability: an intact chain verifies, an edited or deleted entry
is detected at the right link, and audit entries written during a run carry pseudonymized
stems and no Safe-Harbor identifier (design D22).
"""

from __future__ import annotations

from pathlib import Path

from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import Geometry, RequestedOutput, SlideOutcome
from atlas_conductor.dispatch import FakeAdapter, Injection
from atlas_conductor.governance.audit import (
    InMemoryAuditTrail,
    JsonlAuditTrail,
    verify_audit_chain,
)
from atlas_conductor.governance.phi import is_pseudonym, safe_harbor_findings
from atlas_conductor.run import run_job
from atlas_conductor.telemetry import InMemoryTelemetrySink

GEO = Geometry(patch_size=256, target_mag=20)


def _trail_of_three() -> InMemoryAuditTrail:
    trail = InMemoryAuditTrail()
    trail.append("dispatch", {"job_id": "j", "slide_stem": "slide_abc", "detail": "first"})
    trail.append("recovery-decision", {"job_id": "j", "slide_stem": "slide_abc", "detail": "retry"})
    trail.append("hitl-hold", {"job_id": "j", "slide_stem": "slide_abc", "detail": "force"})
    return trail


def test_intact_trail_verifies() -> None:
    trail = _trail_of_three()
    verification = verify_audit_chain(trail.entries())
    assert verification.intact
    assert verification.broken_index is None


def test_edited_entry_is_detected_at_the_right_link() -> None:
    entries = _trail_of_three().entries()
    entries[1]["payload"]["detail"] = "tampered"  # edit the middle entry in place
    verification = verify_audit_chain(entries)
    assert not verification.intact
    assert verification.broken_index == 1


def test_deleted_middle_entry_is_detected() -> None:
    entries = _trail_of_three().entries()
    del entries[1]  # remove the middle entry → the successor's prev_hash no longer matches
    verification = verify_audit_chain(entries)
    assert not verification.intact
    assert verification.broken_index == 1


def test_jsonl_trail_persists_and_verifies(tmp_path: Path) -> None:
    trail = JsonlAuditTrail(tmp_path / "audit.jsonl")
    trail.append("dispatch", {"job_id": "j", "slide_stem": "slide_abc", "detail": "first"})
    trail.append("dispatch", {"job_id": "j", "slide_stem": "slide_def", "detail": "second"})
    # A fresh reader over the same file sees an intact chain.
    reread = JsonlAuditTrail(tmp_path / "audit.jsonl")
    assert verify_audit_chain(reread.entries()).intact


def test_run_audit_entries_are_pseudonymized_and_phi_free(tmp_path: Path) -> None:
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    (cohort / "s.svs").write_bytes(b"fake-wsi")
    config = JobConfig(
        input_dir=cohort,
        output_dir=tmp_path / "out",
        requested_output=RequestedOutput.FEATURES,
        geometry=GEO,
        encoders=("resnet50",),
        unattended=True,  # let the gated recovery ladder run so audit entries accumulate
    )
    audit = InMemoryAuditTrail()
    adapter = FakeAdapter(injections={"s": Injection("nan", label="nan")})
    result = run_job(config, InMemoryTelemetrySink(), adapter=adapter, audit=audit)

    assert result.count(SlideOutcome.QUARANTINED) == 1
    entries = audit.entries()
    assert entries  # consequential actions were recorded
    assert verify_audit_chain(entries).intact
    for entry in entries:
        stem = entry["payload"].get("slide_stem")
        if stem:
            assert is_pseudonym(stem)  # never a raw stem
        assert safe_harbor_findings(str(entry["payload"])) == []  # no identifier in the payload
