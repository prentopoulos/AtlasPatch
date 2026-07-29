"""Tests for the human-in-the-loop confirmation gate (task 3.3).

Covers the ``hitl-gate`` capability: irreversible/expensive actions are held for
confirmation in an attended run, bounded actions proceed unprompted, an unattended run
waives confirmation and records the waiver, a held slide's state is recorded not lost, and
the confirmation policy is a pure function of the action (design D13/D21).
"""

from __future__ import annotations

from pathlib import Path

from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import (
    Geometry,
    ReasonCode,
    RecoveryAction,
    RequestedOutput,
    SlideOutcome,
)
from atlas_conductor.dispatch import FakeAdapter, Injection
from atlas_conductor.governance.audit import InMemoryAuditTrail
from atlas_conductor.governance.hitl import requires_confirmation
from atlas_conductor.run import run_job
from atlas_conductor.telemetry import InMemoryTelemetrySink

GEO = Geometry(patch_size=256, target_mag=20)
ENC = ("resnet50",)


def _config(cohort: Path, out: Path, *, unattended: bool = False) -> JobConfig:
    return JobConfig(
        input_dir=cohort,
        output_dir=out,
        requested_output=RequestedOutput.FEATURES,
        geometry=GEO,
        encoders=ENC,
        unattended=unattended,
    )


def _cohort(tmp_path: Path, stem: str = "s") -> Path:
    cohort = tmp_path / "cohort"
    cohort.mkdir(parents=True, exist_ok=True)
    (cohort / f"{stem}.svs").write_bytes(b"fake-wsi")
    return cohort


def test_policy_matches_the_taxonomy_exactly() -> None:
    gated = {a for a in RecoveryAction if requires_confirmation(a)}
    assert gated == {
        RecoveryAction.FORCE_REPROCESS,
        RecoveryAction.BLOCK_JOB,
        RecoveryAction.QUARANTINE_ITEM,
    }
    # The rest proceed autonomously.
    assert not requires_confirmation(RecoveryAction.RETRY_AS_IS)
    assert not requires_confirmation(RecoveryAction.RETRY_WITH_MUTATION)
    assert not requires_confirmation(RecoveryAction.MARK_DEPENDENTS_BLOCKED)
    assert not requires_confirmation(RecoveryAction.BLOCK_ITEM)


def test_force_reprocess_is_held_in_an_attended_run(tmp_path: Path) -> None:
    cohort = _cohort(tmp_path)
    telemetry = InMemoryTelemetrySink()
    audit = InMemoryAuditTrail()
    # A structural-invalid slide would be force-reprocessed → an attended run must hold it.
    adapter = FakeAdapter(injections={"s": Injection("nan", label="nan")})

    result = run_job(_config(cohort, tmp_path / "out"), telemetry, adapter=adapter, audit=audit)

    slide = result.slides[0]
    assert slide.outcome is SlideOutcome.BLOCKED
    assert slide.reason is ReasonCode.AWAITING_CONFIRMATION
    # The irreversible action was recorded as held, and never applied.
    actions = [e["action"] for e in audit.entries()]
    assert "hitl-hold" in actions
    assert "recovery-decision" not in actions  # apply_recovery was not reached


def test_held_slide_state_is_recorded_not_lost(tmp_path: Path) -> None:
    cohort = _cohort(tmp_path)
    telemetry = InMemoryTelemetrySink()
    adapter = FakeAdapter(injections={"s": Injection("nan", label="nan")})

    run_job(
        _config(cohort, tmp_path / "out"), telemetry, adapter=adapter, audit=InMemoryAuditTrail()
    )

    # The held state is present in telemetry (an outcome and a verdict), not dropped.
    held = [r for r in telemetry.slide_stage_outcomes if r.reason_code == "awaiting-confirmation"]
    assert held, "the held slide must be recorded in telemetry"
    verdicts = [e for e in telemetry.agent_events if e.reason_code == "awaiting-confirmation"]
    assert verdicts


def test_bounded_retry_proceeds_without_confirmation(tmp_path: Path) -> None:
    cohort = _cohort(tmp_path)
    telemetry = InMemoryTelemetrySink()
    audit = InMemoryAuditTrail()
    # A transient OOM on the first attempt only → bounded retry_with_mutation → not gated.
    adapter = FakeAdapter(
        injections={"s": Injection("oom", fail_until_attempt=1, label="cuda-oom")}
    )

    result = run_job(_config(cohort, tmp_path / "out"), telemetry, adapter=adapter, audit=audit)

    assert result.count(SlideOutcome.VALID) == 1  # recovered autonomously, attended
    actions = [e["action"] for e in audit.entries()]
    assert "hitl-hold" not in actions  # no human prompt for a bounded action


def test_unattended_run_waives_confirmation_and_logs_the_waiver(tmp_path: Path) -> None:
    cohort = _cohort(tmp_path)
    telemetry = InMemoryTelemetrySink()
    audit = InMemoryAuditTrail()
    adapter = FakeAdapter(injections={"s": Injection("nan", label="nan")})

    result = run_job(
        _config(cohort, tmp_path / "out", unattended=True), telemetry, adapter=adapter, audit=audit
    )

    # The gated force-then-quarantine ladder runs to completion under the waiver.
    assert result.count(SlideOutcome.QUARANTINED) == 1
    actions = [e["action"] for e in audit.entries()]
    assert "hitl-waiver" in actions
    assert "hitl-hold" not in actions
