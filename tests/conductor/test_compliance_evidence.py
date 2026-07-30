"""Tests for the run-scoped compliance evidence bundle (task 4.3; design D-CMP-3/D-CMP-4).

The bundle agrees with ``export-report`` on a run (shared-read-path invariant), verifies the
audit chain rather than trusting it (intact on an untampered trail, broken when an entry is
altered), and carries only PHI-free operational metadata — no raw identifier, pixel, mask, or
embedding.
"""

from __future__ import annotations

import json
from pathlib import Path

from atlas_conductor.compliance.evidence import build_evidence, export_dossier, render_json
from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import Geometry, RequestedOutput
from atlas_conductor.dispatch import FakeAdapter, Injection
from atlas_conductor.governance.audit import JsonlAuditTrail
from atlas_conductor.governance.phi import is_pseudonym
from atlas_conductor.gui.export import export_report
from atlas_conductor.run import run_job
from atlas_conductor.telemetry import JsonlTelemetrySink

GEO = Geometry(patch_size=256, target_mag=20)


def _run_cohort(tmp_path: Path, stems: list[str]) -> Path:
    """Run a cohort writing JSONL telemetry + an audit trail into one telemetry dir."""
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    for stem in stems:
        (cohort / f"{stem}.svs").write_bytes(b"fake-wsi")
    tele = tmp_path / "tele"
    config = JobConfig(
        input_dir=cohort,
        output_dir=tmp_path / "out",
        requested_output=RequestedOutput.FEATURES,
        geometry=GEO,
        encoders=("resnet50",),
        unattended=True,  # let the gated recovery ladder run so HITL waivers are recorded
    )
    audit = JsonlAuditTrail(tele / "audit.jsonl")
    # Inject a failure on the first slide so recovery + a gated (waived) action is logged.
    adapter = FakeAdapter(injections={stems[0]: Injection("nan", label="nan")})
    run_job(config, JsonlTelemetrySink(tele), adapter=adapter, audit=audit)
    return tele


def test_bundle_and_report_agree_on_a_run(tmp_path: Path) -> None:
    tele = _run_cohort(tmp_path, ["a", "b", "c"])
    bundle = build_evidence(tele)
    report = json.loads(export_report(tele, fmt="json"))["runs"]

    assert len(bundle.runs) == len(report) == 1
    run_evidence = bundle.runs[0]
    run_report = report[0]
    # Cohort counts identical to the report (shared read path).
    assert run_evidence.cohort_size == run_report["cohort_size"]
    assert run_evidence.counts == run_report["counts"]
    # Per-slide verdicts identical, keyed by stem.
    report_verdicts = {
        s["slide_stem"]: (s["outcome"], s["reason_code"]) for s in run_report["slides"]
    }
    bundle_verdicts = {s.slide_stem: (s.outcome, s.reason_code) for s in run_evidence.slides}
    assert bundle_verdicts == report_verdicts


def test_bundle_carries_governance_decisions_and_verifies_intact(tmp_path: Path) -> None:
    tele = _run_cohort(tmp_path, ["a", "b"])
    bundle = build_evidence(tele)

    assert bundle.audit_chain.intact  # untampered trail verifies intact
    assert bundle.audit_entry_count > 0
    run = bundle.runs[0]
    # The gated recovery action was waived under the unattended run and recorded.
    assert run.decision_counts["hitl-waiver"] >= 1
    assert any(d.action == "hitl-waiver" for d in run.governance_decisions)


def test_bundle_reports_a_tampered_chain_as_broken(tmp_path: Path) -> None:
    tele = _run_cohort(tmp_path, ["a", "b"])
    trail_path = tele / "audit.jsonl"
    rows = [
        json.loads(line) for line in trail_path.read_text(encoding="utf-8").splitlines() if line
    ]
    assert rows
    # Alter an entry's payload in place without recomputing its hash → chain must break.
    rows[0]["payload"]["detail"] = "tampered after the fact"
    trail_path.write_text(
        "\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n", encoding="utf-8"
    )

    bundle = build_evidence(tele)
    assert not bundle.audit_chain.intact
    assert bundle.audit_chain.broken_index == 0


def test_bundle_is_phi_free_for_an_identifier_stem(tmp_path: Path) -> None:
    # A cohort whose stem is itself a Safe-Harbor identifier: the bundle must show pseudonyms.
    tele = _run_cohort(tmp_path, ["987654321", "b"])
    bundle = build_evidence(tele)

    for slide in bundle.runs[0].slides:
        assert is_pseudonym(slide.slide_stem)
    for fmt in ("json", "html"):
        rendered = export_dossier(tele, fmt=fmt)
        assert "987654321" not in rendered  # raw identifier provably absent
        assert "<img" not in rendered.lower()  # no pixels
        assert "<script" not in rendered.lower()  # no scripts (self-contained HTML)
    # No confidence/score/probability leaks into the machine-readable body.
    doc = render_json(bundle)
    for banned in ("confidence", "probability", "embedding"):
        assert banned not in doc


def test_bundle_attaches_the_control_register_summary(tmp_path: Path) -> None:
    tele = _run_cohort(tmp_path, ["a"])
    bundle = build_evidence(tele)
    assert bundle.controls.well_formed
    assert bundle.controls.total == sum(bundle.controls.by_framework.values())
    assert bundle.controls.control_ids


def test_empty_telemetry_builds_a_clean_bundle(tmp_path: Path) -> None:
    bundle = build_evidence(tmp_path / "empty")
    assert bundle.runs == []
    assert bundle.audit_chain.intact  # a zero-length chain verifies trivially
    assert bundle.audit_entry_count == 0
