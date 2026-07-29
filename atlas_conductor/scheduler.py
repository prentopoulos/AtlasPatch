"""The scheduler control loop (task 5.5 — cohort first pass, slice A1).

The scheduler is a deterministic in-process resource governor, not an agent (design
D8). Slice A1 implements the cohort-directory first pass (design D2): the runnable
slides are dispatched as one invocation over the input directory to amortize model
load, and then per-slide outcome accounting is derived from the filesystem via the
validity predicate — independent of dispatch granularity, and authoritative over any
CLI exit code (design D3, output-validation spec).

Per-file recovery retries and concurrency governance are slice A3; this loop runs the
first pass once and reports what the filesystem shows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from atlas_conductor.agents import Agent
from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import (
    STAGES_FOR_OUTPUT,
    Decision,
    Outcome,
    Plan,
    PlanNode,
    ReasonCode,
    SlideOutcome,
    Task,
    Verdict,
    make_idempotency_key,
)
from atlas_conductor.dispatch import ExecutionAdapter, Worker
from atlas_conductor.telemetry import (
    AgentEventRecord,
    JobRecord,
    SlideStageOutcomeRecord,
    TelemetrySink,
    ValidationResultRecord,
)
from atlas_conductor.validation import validate_output


@dataclass
class SlideResult:
    """The terminal accounting for one slide after the run."""

    slide_stem: str
    outcome: SlideOutcome
    reason: ReasonCode
    detail: str = ""


@dataclass
class RunResult:
    """The whole run's result: per-slide outcomes and cohort counts."""

    job_id: str
    plan: Plan
    slides: list[SlideResult] = field(default_factory=list)

    def count(self, outcome: SlideOutcome) -> int:
        return sum(1 for s in self.slides if s.outcome == outcome)

    @property
    def cohort_size(self) -> int:
        return len(self.slides)


class Scheduler:
    """Run a reconciled plan: dispatch the first pass, then account per slide."""

    def __init__(
        self,
        config: JobConfig,
        adapter: ExecutionAdapter,
        telemetry: TelemetrySink,
        adapter_name: str = "fake",
    ) -> None:
        self._config = config
        self._adapter = adapter
        self._telemetry = telemetry
        self._adapter_name = adapter_name

    def run(self, plan: Plan) -> RunResult:
        started_at = datetime.now(timezone.utc).isoformat()
        self._telemetry.record_agent_event(
            AgentEventRecord(
                job_id=plan.job_id,
                agent=Agent.SCHEDULER.value,
                event="run-start",
                detail=f"adapter={self._adapter_name}",
            )
        )

        if plan.is_blocked:
            result = self._blocked_result(plan)
        else:
            self._dispatch_first_pass(plan)
            result = self._account_cohort(plan)

        self._record_job(plan, result, started_at)
        return result

    def _dispatch_first_pass(self, plan: Plan) -> Outcome | None:
        """Dispatch the runnable slides as one cohort-directory invocation."""
        terminal_stage = STAGES_FOR_OUTPUT[plan.requested_output][-1]
        runnable = plan.runnable_nodes(terminal_stage)
        if not runnable:
            return None

        targets = tuple(node.target for node in runnable)
        task = Task(
            stage=terminal_stage,
            command=runnable[0].command,
            requested_output=plan.requested_output,
            input_path=plan.input_dir,
            output_dir=plan.output_dir,
            targets=targets,
            geometry=plan.geometry,
            encoders=plan.encoders,
            idempotency_key=make_idempotency_key(
                plan.job_id, "cohort-first-pass", terminal_stage, plan.geometry
            ),
        )
        worker = Worker(self._adapter, self._telemetry, plan.job_id)
        for node in runnable:
            node.attempts += 1
        return worker.execute(task)

    def _account_cohort(self, plan: Plan) -> RunResult:
        """Derive each slide's terminal outcome from the filesystem (design D2/D3)."""
        result = RunResult(job_id=plan.job_id, plan=plan)
        terminal_stage = STAGES_FOR_OUTPUT[plan.requested_output][-1]
        for node in plan.nodes_for(terminal_stage):
            verdict = validate_output(
                node.target.expected_h5_path,
                plan.geometry,
                plan.requested_output,
                plan.encoders,
            )
            result.slides.append(self._slide_result(plan, node, verdict))
        return result

    def _slide_result(self, plan: Plan, node: PlanNode, verdict: Verdict) -> SlideResult:
        was_skip = node.decision is Decision.SKIP
        if verdict.valid:
            outcome = SlideOutcome.SKIPPED if was_skip else SlideOutcome.VALID
        elif node.decision is Decision.BLOCKED:
            outcome = SlideOutcome.BLOCKED
        else:
            # First-pass ran but output is not structurally valid. Slice A1 has no
            # recovery, so the slide is quarantined; slice A3 retries before this.
            outcome = SlideOutcome.QUARANTINED

        self._telemetry.record_validation(
            ValidationResultRecord(
                job_id=plan.job_id,
                slide_stem=node.slide_stem,
                stage=node.stage.value,
                requested_output=plan.requested_output.value,
                valid=verdict.valid,
                reason_code=verdict.reason.value,
                detail=verdict.detail,
            )
        )
        self._telemetry.record_slide_stage_outcome(
            SlideStageOutcomeRecord(
                job_id=plan.job_id,
                slide_stem=node.slide_stem,
                stage=node.stage.value,
                command=node.command.value,
                attempt=node.attempts,
                outcome=outcome.value,
                reason_code=verdict.reason.value,
                exit_code=0,
            )
        )
        self._telemetry.record_agent_event(
            AgentEventRecord(
                job_id=plan.job_id,
                agent=Agent.VALIDATOR.value,
                event="verdict",
                slide_stem=node.slide_stem,
                stage=node.stage.value,
                reason_code=verdict.reason.value,
                detail=outcome.value,
            )
        )
        return SlideResult(node.slide_stem, outcome, verdict.reason, verdict.detail)

    def _blocked_result(self, plan: Plan) -> RunResult:
        result = RunResult(job_id=plan.job_id, plan=plan)
        reason = plan.blocked_reason or ReasonCode.EMPTY_COHORT
        for stem in plan.slide_stems() or ["<cohort>"]:
            result.slides.append(
                SlideResult(stem, SlideOutcome.BLOCKED, reason, plan.blocked_detail)
            )
        return result

    def _record_job(self, plan: Plan, result: RunResult, started_at: str) -> None:
        self._telemetry.record_job(
            JobRecord(
                job_id=plan.job_id,
                input_dir=str(plan.input_dir),
                requested_output=plan.requested_output.value,
                patch_size=plan.geometry.patch_size,
                target_mag=plan.geometry.target_mag,
                encoders=",".join(plan.encoders),
                adapter=self._adapter_name,
                status="blocked" if plan.is_blocked else "complete",
                cohort_size=result.cohort_size,
                valid_count=result.count(SlideOutcome.VALID),
                skipped_count=result.count(SlideOutcome.SKIPPED),
                quarantined_count=result.count(SlideOutcome.QUARANTINED),
                blocked_count=result.count(SlideOutcome.BLOCKED),
                started_at=started_at,
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
        )
