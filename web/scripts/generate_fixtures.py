"""Regenerate the committed demo/gated snapshot fixtures for the React observability GUI.

The SPA ships a bundled ``snapshot.json`` so the panels populate out of the box, and a
second *gated* fixture the Playwright guardrail suite asserts over. Both are produced the
*same way a real export is* — seed a telemetry directory with the append-only records, then
run :func:`assemble_snapshot` over it — so the fixtures can never drift from the frozen
``gui-snapshot`` contract (schema version, shape, PHI-free/no-score invariants).

Reproducible: deterministic inputs, deterministic pseudonyms (``pseudonymize_stem`` is a pure
function of ``(stem, job_id)``), stable JSON serialization. Run from the repo root:

    python web/scripts/generate_fixtures.py

It rewrites ``web/src/fixtures/demo-snapshot.json`` and ``web/src/fixtures/gated-snapshot.json``.
No GPU, no slides, no ``atlas_patch`` import — it exercises only the PHI-free telemetry path.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from atlas_conductor.governance.phi import pseudonymize_stem
from atlas_conductor.gui.snapshot import assemble_snapshot
from atlas_conductor.telemetry import (
    AgentEventRecord,
    JobRecord,
    JsonlTelemetrySink,
    MessageFlowRecord,
    SlideStageOutcomeRecord,
    ValidationResultRecord,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "src" / "fixtures"

# Reason codes + human details per terminal outcome, mirroring the validator's structural
# verdicts (never a score). Kept operational so the PHI/no-score guards stay green.
_OUTCOME_DETAIL = {
    "valid": ("valid", "312 patches at 20x"),
    "skipped": ("non_tissue_skip", "below tissue-fraction threshold"),
    "quarantined": ("empty_h5", "0 patches — empty coordinate set"),
    "blocked": ("irreversible_blocked", "HITL gate: would overwrite existing output"),
}

# Which agent authors each trace step, in decision-chain order (trace.py _TRACE_EVENTS).
_STEP_AGENT = {
    "reconcile": "scheduler",
    "dispatch": "worker",
    "verdict": "validator",
    "blocked": "validator",
    "recover": "recovery",
}


def _seed_slide(
    sink: JsonlTelemetrySink,
    job_id: str,
    raw_stem: str,
    outcome: str,
    clock: list[int],
) -> None:
    """Seed one slide's outcome, validation, and ordered decision trace into the sink."""
    stem = pseudonymize_stem(raw_stem, job_id)
    reason_code, detail = _OUTCOME_DETAIL[outcome]

    sink.record_slide_stage_outcome(
        SlideStageOutcomeRecord(
            job_id=job_id,
            slide_stem=stem,
            stage="segment",
            command="segment-and-get-coords",
            attempt=1,
            outcome=outcome,
            reason_code=reason_code,
        )
    )
    sink.record_validation(
        ValidationResultRecord(
            job_id=job_id,
            slide_stem=stem,
            stage="segment",
            requested_output="coords",
            valid=(outcome == "valid"),
            reason_code=reason_code,
            detail=detail,
        )
    )

    # The decision chain: reconcile -> dispatch -> verdict, plus a terminal step for the
    # non-valid outcomes (blocked slides hit the HITL gate; quarantined ones a recovery pass).
    steps = ["reconcile", "dispatch", "verdict"]
    if outcome == "blocked":
        steps.append("blocked")
    elif outcome in ("quarantined", "skipped"):
        steps.append("recover")
    for step in steps:
        clock[0] += 1
        sink.record_agent_event(
            AgentEventRecord(
                job_id=job_id,
                agent=_STEP_AGENT[step],
                event=step,
                slide_stem=stem,
                stage="segment",
                reason_code=reason_code if step in ("verdict", "blocked", "recover") else "",
                timestamp=f"2026-07-30T09:{clock[0]:02d}:00",
            )
        )


def _seed_run(
    directory: Path,
    job_id: str,
    outcomes: list[str],
    *,
    with_message_flow: bool,
) -> None:
    """Seed one full run (job row, per-slide trace, optional inter-agent message flow)."""
    sink = JsonlTelemetrySink(directory)
    counts = {o: outcomes.count(o) for o in ("valid", "skipped", "quarantined", "blocked")}
    sink.record_job(
        JobRecord(
            job_id=job_id,
            input_dir="cohort",
            requested_output="coords",
            patch_size=256,
            target_mag=20,
            encoders="",
            adapter="fake",
            status="completed",
            cohort_size=len(outcomes),
            valid_count=counts["valid"],
            skipped_count=counts["skipped"],
            quarantined_count=counts["quarantined"],
            blocked_count=counts["blocked"],
        )
    )
    clock = [0]
    # A planning event opens the run (no slide -> not part of any slide trace).
    sink.record_agent_event(
        AgentEventRecord(
            job_id=job_id, agent="planner", event="planned", timestamp="2026-07-30T09:00:00"
        )
    )
    for i, outcome in enumerate(outcomes):
        _seed_slide(sink, job_id, f"cohort/{job_id}-{i:03d}.svs", outcome, clock)

    if with_message_flow:
        flow = [
            ("planner", "worker", "dispatch"),
            ("worker", "validator", "verify"),
            ("validator", "recovery", "quarantine"),
            ("recovery", "worker", "retry"),
            ("worker", "validator", "verify"),
        ]
        for j, (frm, to, kind) in enumerate(flow):
            sink.record_message_flow(
                MessageFlowRecord(
                    job_id=job_id,
                    from_agent=frm,
                    to_agent=to,
                    message_type=kind,
                    correlation_id=f"c{j}",
                    timestamp=f"2026-07-30T09:{40 + j:02d}:00",
                )
            )


def _write(name: str, payload: dict) -> None:
    path = FIXTURES_DIR / name
    # Force LF (newline="") so the committed fixtures are byte-identical on Windows and Linux —
    # the bundle inlines them, so a CRLF here would break the CI build-and-diff staleness gate.
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    print(f"wrote {path.relative_to(Path.cwd())}  ({len(payload['runs'])} run(s))")


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    # Demo: a rich cohort exercising all four verdicts + message flow, plus a second, quieter
    # run with no recorded message flow (so the choreography panel's degrade path is visible).
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        _seed_run(
            directory,
            "job-cohort-a",
            ["valid", "valid", "valid", "valid", "valid", "skipped", "quarantined", "blocked"],
            with_message_flow=True,
        )
        _seed_run(
            directory,
            "job-cohort-b",
            ["valid", "valid", "valid", "quarantined"],
            with_message_flow=False,
        )
        _write("demo-snapshot.json", assemble_snapshot(directory))

    # Gated: a single small run whose stems went through the PHI gate — the Playwright suite
    # asserts the rendered DOM shows only these pseudonyms and no raw identifier.
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        _seed_run(
            directory,
            "job-gated",
            ["valid", "quarantined", "blocked"],
            with_message_flow=True,
        )
        _write("gated-snapshot.json", assemble_snapshot(directory))


if __name__ == "__main__":
    main()
