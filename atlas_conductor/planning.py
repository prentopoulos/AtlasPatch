"""The planner (tasks 4.1, 4.2).

The planner turns a job config plus the discovered cohort into a reconciled plan DAG.
It is the single writer of plan state (design D6). Two responsibilities land in slice
A1:

* **Stage-DAG construction (4.1):** each slide gets one node per logical stage for the
  requested output (`coords` → `segment`; `features` → `segment` → `embed` with an
  `embed`-depends-on-`segment` edge), and each node records the CLI command its stage
  dispatches onto via the stage→command map (design D1). The plan is never a flat list
  of commands.
* **State reconciliation (4.2):** for each slide the planner runs the validity
  predicate against the *requested* output (branch-on-output, design D4) and marks the
  slide ``skip`` (already valid), ``reuse`` (coords valid, only embed needed — relying
  on AtlasPatch's own coord reuse), or ``run``.

Plan-time geometry-conflict blocking (4.3) and the input-admissibility gate (4.6) are
slice A2; recovery plan-delta integration (4.4) is slice A3. The predicate already
returns a ``geometry-mismatch`` reason, so A2's blocking is a decision on top of an
existing signal, not a new computation.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from atlas_conductor.agents import Agent
from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import (
    COMMAND_FOR_OUTPUT,
    STAGES_FOR_OUTPUT,
    Decision,
    Plan,
    PlanNode,
    ReasonCode,
    RequestedOutput,
    Stage,
    TaskTarget,
    Verdict,
    make_idempotency_key,
)
from atlas_conductor.telemetry import (
    AgentEventRecord,
    TelemetrySink,
    ValidationResultRecord,
)
from atlas_conductor.validation import patch_h5_path, validate_output

# WSI file extensions AtlasPatch can consume — the admissibility allowlist (design D16,
# consumed by the slice-A2 gate; defined here as the planner owns cohort discovery).
WSI_EXTENSIONS: frozenset[str] = frozenset(
    {".svs", ".tif", ".tiff", ".ndpi", ".scn", ".mrxs", ".vms", ".vmu", ".svslide", ".bif"}
)


class Planner:
    """Build a reconciled plan from a job config and a discovered cohort."""

    def __init__(self, telemetry: TelemetrySink, job_id: str | None = None) -> None:
        self._telemetry = telemetry
        self.job_id = job_id or uuid.uuid4().hex[:12]

    def build_plan(self, config: JobConfig, slide_paths: list[Path]) -> Plan:
        """Construct and reconcile the plan for ``config`` over ``slide_paths``."""
        plan = Plan(
            job_id=self.job_id,
            requested_output=config.requested_output,
            geometry=config.geometry,
            encoders=config.encoders,
            input_dir=config.input_dir,
            output_dir=config.output_dir,
        )
        command = COMMAND_FOR_OUTPUT[config.requested_output]
        stages = STAGES_FOR_OUTPUT[config.requested_output]

        for wsi_path in sorted(slide_paths):
            stem = wsi_path.stem
            target = TaskTarget(
                slide_stem=stem,
                wsi_path=wsi_path,
                expected_h5_path=patch_h5_path(config.output_dir, stem),
            )
            verdict = self._reconcile_slide(config, target)
            prev_node_id: str | None = None
            for stage in stages:
                node = PlanNode(
                    node_id=make_idempotency_key(self.job_id, stem, stage, config.geometry),
                    slide_stem=stem,
                    stage=stage,
                    command=command,
                    target=target,
                    dependencies=(prev_node_id,) if prev_node_id else (),
                    attempt_budget=config.attempt_budget,
                )
                self._apply_decision(node, stage, config.requested_output, verdict)
                plan.nodes.append(node)
                prev_node_id = node.node_id

        self._telemetry.record_agent_event(
            AgentEventRecord(
                job_id=self.job_id,
                agent=Agent.PLANNER.value,
                event="plan-built",
                detail=(
                    f"cohort={len(slide_paths)} output={config.requested_output.value} "
                    f"nodes={len(plan.nodes)}"
                ),
            )
        )
        return plan

    def _reconcile_slide(self, config: JobConfig, target: TaskTarget) -> Verdict:
        """Evaluate the validity predicate for the slide's requested output."""
        verdict = validate_output(
            target.expected_h5_path,
            config.geometry,
            config.requested_output,
            config.encoders,
        )
        self._telemetry.record_validation(
            ValidationResultRecord(
                job_id=self.job_id,
                slide_stem=target.slide_stem,
                stage="plan-reconcile",
                requested_output=config.requested_output.value,
                valid=verdict.valid,
                reason_code=verdict.reason.value,
                detail=verdict.detail,
            )
        )
        return verdict

    def _apply_decision(
        self,
        node: PlanNode,
        stage: Stage,
        requested_output: RequestedOutput,
        verdict: Verdict,
    ) -> None:
        """Set a node's decision from the slide's reconciliation verdict."""
        if verdict.valid:
            node.decision = Decision.SKIP
            node.reason = ReasonCode.VALID
            return

        # Coords already valid but features missing/invalid → reuse coords, only embed.
        # We detect "coords valid" by re-checking coords-only validity cheaply.
        if requested_output is RequestedOutput.FEATURES and verdict.reason in (
            ReasonCode.MISSING_FEATURES,
            ReasonCode.ROW_MISMATCH,
            ReasonCode.NAN_FEATURES,
        ):
            if stage is Stage.SEGMENT:
                node.decision = Decision.SKIP
                node.reason = ReasonCode.VALID
            else:  # EMBED
                node.decision = Decision.REUSE
                node.reason = verdict.reason
            return

        node.decision = Decision.RUN
        node.reason = verdict.reason


def discover_cohort(input_dir: Path) -> list[Path]:
    """Return WSI-extension files directly under ``input_dir`` (non-recursive).

    Shallow discovery matching AtlasPatch's directory mode. The admissibility gate
    (slice A2) decides what to do with an empty or non-WSI result; here we only list.
    """
    directory = Path(input_dir)
    if not directory.is_dir():
        return []
    return sorted(
        p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in WSI_EXTENSIONS
    )
