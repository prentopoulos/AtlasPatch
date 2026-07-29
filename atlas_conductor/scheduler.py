"""The scheduler control loop (task 5.5).

The scheduler is a deterministic in-process resource governor, not an agent (design
D8). It runs the cohort-directory first pass (design D2) — the runnable slides as one
invocation over the input directory to amortize model load — and then drives per-slide,
stage-aware recovery with per-file retries. Per-slide outcome accounting is always
derived from the filesystem via the validity predicate (design D3), authoritative over
any CLI exit code.

Recovery is stage-aware: for each slide the scheduler walks the stage DAG in order,
and for the first failing stage it asks the recovery agent to classify the failure and
propose a bounded action (design D7). The **planner** applies the proposal (design D6);
the scheduler only dispatches the resulting per-file retry. A quarantined/blocked stage
marks its downstream stages dependency-blocked, so an embed is never scheduled after its
segment fails (failure-recovery spec). Every recovery attempt is logged with its
`(signature, classification, action, resolved)` tuple so the telemetry is a labeled
recovery dataset (design D14).
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
    RecoveryAction,
    RequestedOutput,
    SlideOutcome,
    Stage,
    Task,
    Verdict,
    make_idempotency_key,
)
from atlas_conductor.dispatch import ExecutionAdapter, Worker
from atlas_conductor.planning import Planner
from atlas_conductor.recovery import RecoveryProposal, classify, propose
from atlas_conductor.telemetry import (
    AgentEventRecord,
    JobRecord,
    SlideStageOutcomeRecord,
    TelemetrySink,
    ValidationResultRecord,
)
from atlas_conductor.validation import validate_output

# Which requested-output the predicate evaluates for each stage's validity.
_STAGE_OUTPUT = {Stage.SEGMENT: RequestedOutput.COORDS, Stage.EMBED: RequestedOutput.FEATURES}


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
    """Run a reconciled plan: first pass, then stage-aware per-file recovery."""

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
        self._worker = Worker(adapter, telemetry, "")  # rebound per run in run()

    def run(self, plan: Plan) -> RunResult:
        started_at = datetime.now(timezone.utc).isoformat()
        self._worker = Worker(self._adapter, self._telemetry, plan.job_id)
        self._planner = Planner(self._telemetry, job_id=plan.job_id)
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
            first_pass = self._dispatch_first_pass(plan)
            result = self._recover_and_account(plan, first_pass)

        self._record_job(plan, result, started_at)
        return result

    # -- first pass --------------------------------------------------------------

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
        for node in runnable:
            node.attempts += 1
            self._telemetry.record_agent_event(
                AgentEventRecord(
                    job_id=plan.job_id,
                    agent=Agent.WORKER.value,
                    event="dispatch",
                    slide_stem=node.slide_stem,
                    stage=node.stage.value,
                    detail=f"{node.decision.value} command={node.command.value} "
                    f"attempt={node.attempts}",
                )
            )
        return self._worker.execute(task)

    # -- recovery + accounting ---------------------------------------------------

    def _recover_and_account(self, plan: Plan, first_pass: Outcome | None) -> RunResult:
        result = RunResult(job_id=plan.job_id, plan=plan)
        stages = STAGES_FOR_OUTPUT[plan.requested_output]
        nodes_by_slide: dict[str, dict[Stage, PlanNode]] = {}
        for node in plan.nodes:
            nodes_by_slide.setdefault(node.slide_stem, {})[node.stage] = node
        for stem in plan.slide_stems():
            result.slides.append(
                self._recover_slide(plan, stem, nodes_by_slide[stem], stages, first_pass)
            )
        return result

    def _recover_slide(
        self,
        plan: Plan,
        stem: str,
        nodes: dict[Stage, PlanNode],
        stages: tuple[Stage, ...],
        first_pass: Outcome | None,
    ) -> SlideResult:
        last_outcome = first_pass
        for stage in stages:
            node = nodes[stage]
            # A stage blocked before any attempt is a plan-time block (admissibility /
            # geometry) or a dependency block; account it directly.
            if node.decision is Decision.BLOCKED and not node.mutation_history:
                return self._finalize_blocked(plan, node)

            pending: tuple[RecoveryProposal, str | None] | None = None
            while True:
                verdict = self._validate_stage(plan, node)
                if pending is not None:
                    proposal, label = pending
                    self._record_recovery_outcome(plan, node, proposal, label, verdict.valid)
                    pending = None
                self._record_validation(plan, node, verdict)
                if verdict.valid:
                    break

                classification, signature = classify(last_outcome, verdict)
                proposal = propose(classification, signature, node, last_outcome)
                label = last_outcome.injected_label if last_outcome else None
                self._planner.apply_recovery(plan, node, proposal)

                if node.decision is Decision.BLOCKED:  # quarantine / block (terminal)
                    self._record_recovery_outcome(plan, node, proposal, label, resolved=False)
                    return self._terminal_recovery_result(plan, node, proposal.action)

                last_outcome = self._dispatch_retry(plan, node)
                node.attempts += 1
                pending = (proposal, label)

        return self._finalize_valid(plan, stem, nodes, stages)

    def _validate_stage(self, plan: Plan, node: PlanNode) -> Verdict:
        return validate_output(
            node.target.expected_h5_path,
            plan.geometry,
            _STAGE_OUTPUT[node.stage],
            plan.encoders if node.stage is Stage.EMBED else (),
        )

    def _dispatch_retry(self, plan: Plan, node: PlanNode) -> Outcome:
        """Dispatch a single-slide (per-file) retry for one node (design D2)."""
        task = Task(
            stage=node.stage,
            command=node.command,
            requested_output=plan.requested_output,
            input_path=node.target.wsi_path,  # per-file, not the cohort directory
            output_dir=plan.output_dir,
            targets=(node.target,),
            geometry=plan.geometry,
            encoders=plan.encoders,
            tuning=node.tuning,
            attempt=node.attempts + 1,
            mutation_history=node.mutation_history,
            idempotency_key=make_idempotency_key(
                plan.job_id, node.slide_stem, node.stage, plan.geometry
            ),
        )
        return self._worker.execute(task)

    # -- finalizers --------------------------------------------------------------

    def _finalize_valid(
        self, plan: Plan, stem: str, nodes: dict[Stage, PlanNode], stages: tuple[Stage, ...]
    ) -> SlideResult:
        terminal = nodes[stages[-1]]
        outcome = SlideOutcome.SKIPPED if terminal.attempts == 0 else SlideOutcome.VALID
        self._record_slide_outcome(plan, terminal, outcome, ReasonCode.VALID)
        self._record_agent_verdict(plan, terminal, ReasonCode.VALID, outcome)
        return SlideResult(stem, outcome, ReasonCode.VALID)

    def _finalize_blocked(self, plan: Plan, node: PlanNode) -> SlideResult:
        reason = node.reason or ReasonCode.DEPENDENCY_BLOCKED
        self._record_slide_outcome(plan, node, SlideOutcome.BLOCKED, reason)
        self._record_agent_verdict(plan, node, reason, SlideOutcome.BLOCKED, agent=Agent.PLANNER)
        return SlideResult(node.slide_stem, SlideOutcome.BLOCKED, reason, node.detail)

    def _terminal_recovery_result(
        self, plan: Plan, node: PlanNode, action: RecoveryAction
    ) -> SlideResult:
        outcome = (
            SlideOutcome.QUARANTINED
            if action is RecoveryAction.QUARANTINE_ITEM
            else SlideOutcome.BLOCKED
        )
        reason = node.reason or ReasonCode.ATTEMPTS_EXHAUSTED
        self._record_slide_outcome(plan, node, outcome, reason)
        self._record_agent_verdict(plan, node, reason, outcome, agent=Agent.RECOVERY)
        return SlideResult(node.slide_stem, outcome, reason, node.detail)

    def _blocked_result(self, plan: Plan) -> RunResult:
        result = RunResult(job_id=plan.job_id, plan=plan)
        reason = plan.blocked_reason or ReasonCode.EMPTY_COHORT
        for stem in plan.slide_stems() or ["<cohort>"]:
            result.slides.append(
                SlideResult(stem, SlideOutcome.BLOCKED, reason, plan.blocked_detail)
            )
        return result

    # -- telemetry ---------------------------------------------------------------

    def _record_validation(self, plan: Plan, node: PlanNode, verdict: Verdict) -> None:
        self._telemetry.record_validation(
            ValidationResultRecord(
                job_id=plan.job_id,
                slide_stem=node.slide_stem,
                stage=node.stage.value,
                requested_output=_STAGE_OUTPUT[node.stage].value,
                valid=verdict.valid,
                reason_code=verdict.reason.value,
                detail=verdict.detail,
            )
        )

    def _record_slide_outcome(
        self, plan: Plan, node: PlanNode, outcome: SlideOutcome, reason: ReasonCode
    ) -> None:
        self._telemetry.record_slide_stage_outcome(
            SlideStageOutcomeRecord(
                job_id=plan.job_id,
                slide_stem=node.slide_stem,
                stage=node.stage.value,
                command=node.command.value,
                attempt=node.attempts,
                outcome=outcome.value,
                reason_code=reason.value,
                exit_code=0,
            )
        )

    def _record_recovery_outcome(
        self,
        plan: Plan,
        node: PlanNode,
        proposal: RecoveryProposal,
        injected_label: str | None,
        resolved: bool,
    ) -> None:
        """Log the labeled recovery tuple (signature, classification, action, resolved)."""
        self._telemetry.record_slide_stage_outcome(
            SlideStageOutcomeRecord(
                job_id=plan.job_id,
                slide_stem=node.slide_stem,
                stage=node.stage.value,
                command=node.command.value,
                attempt=node.attempts,
                outcome=("valid" if resolved else "unresolved"),
                reason_code=(node.reason.value if node.reason else "recovering"),
                signature=proposal.signature,
                classification=proposal.classification.value,
                action=proposal.action.value,
                resolved=resolved,
                injected_label=injected_label,
            )
        )

    def _record_agent_verdict(
        self,
        plan: Plan,
        node: PlanNode,
        reason: ReasonCode,
        outcome: SlideOutcome,
        agent: Agent = Agent.VALIDATOR,
    ) -> None:
        self._telemetry.record_agent_event(
            AgentEventRecord(
                job_id=plan.job_id,
                agent=agent.value,
                event="verdict",
                slide_stem=node.slide_stem,
                stage=node.stage.value,
                reason_code=reason.value,
                detail=outcome.value,
            )
        )

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
