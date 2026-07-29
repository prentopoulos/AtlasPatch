"""The planner (tasks 4.1, 4.2, 4.3, 4.6).

The planner turns a job config plus the discovered cohort into a reconciled plan DAG.
It is the single writer of plan state (design D6). Slice A1 delivered stage-DAG
construction (4.1) and skip/run/reuse reconciliation (4.2); slice A2 adds the two
plan-time *block* decisions:

* **Geometry-conflict blocking (4.3):** when a slide's existing HDF5 was produced with
  a different patch size or target magnification, the planner marks it ``blocked`` with
  an actionable message rather than dispatching a run AtlasPatch would reject. The
  validity predicate already returns a ``geometry-mismatch`` reason (task 3.2), so this
  is a decision on an existing signal.
* **Input-admissibility gate (4.6, design D16):** before dispatch the planner rejects
  inadmissible cohorts/inputs — an empty cohort (`empty-cohort`), a directory with no
  WSI-extension files (`no-wsi-files`), or an unreadable/zero-byte candidate file
  (`unreadable-input`). The check is deliberately shallow (extension allowlist +
  existence + non-zero size + readability); it performs no slide decode, so deep slide
  validation remains AtlasPatch's responsibility.

Each per-slide reconciliation decision is recorded as an ``agent_events`` record so the
decision trace (design D15, task 8.3) can reconstruct the ordered steps per slide.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
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

# WSI file extensions AtlasPatch can consume — the admissibility allowlist (design D16).
WSI_EXTENSIONS: frozenset[str] = frozenset(
    {".svs", ".tif", ".tiff", ".ndpi", ".scn", ".mrxs", ".vms", ".vmu", ".svslide", ".bif"}
)


@dataclass
class Admissibility:
    """The result of the shallow plan-time admissibility check (design D16)."""

    cohort_block: ReasonCode | None = None  # EMPTY_COHORT / NO_WSI_FILES / None
    detail: str = ""
    admissible: list[Path] = field(default_factory=list)
    # (path, reason, detail) for each individually-inadmissible WSI candidate.
    inadmissible: list[tuple[Path, ReasonCode, str]] = field(default_factory=list)


def check_admissibility(input_dir: Path) -> Admissibility:
    """Shallowly assess whether a cohort directory is admissible for dispatch.

    Never decodes a slide — only extension, existence, size, and readability.
    """
    directory = Path(input_dir)
    if not directory.is_dir():
        return Admissibility(
            cohort_block=ReasonCode.EMPTY_COHORT,
            detail=f"cohort directory does not exist: {directory}",
        )

    entries = sorted(directory.iterdir())
    if not entries:
        return Admissibility(
            cohort_block=ReasonCode.EMPTY_COHORT, detail=f"cohort directory is empty: {directory}"
        )

    wsi_files = [p for p in entries if p.is_file() and p.suffix.lower() in WSI_EXTENSIONS]
    if not wsi_files:
        return Admissibility(
            cohort_block=ReasonCode.NO_WSI_FILES,
            detail=(
                f"no files matching the WSI extension allowlist in {directory} "
                f"({', '.join(sorted(WSI_EXTENSIONS))})"
            ),
        )

    result = Admissibility()
    for path in wsi_files:
        reason_detail = _inadmissible_reason(path)
        if reason_detail is None:
            result.admissible.append(path)
        else:
            result.inadmissible.append((path, ReasonCode.UNREADABLE_INPUT, reason_detail))
    return result


def _inadmissible_reason(path: Path) -> str | None:
    """Return a reason string if the file is unreadable/zero-byte, else None (no decode)."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        return f"cannot stat file: {exc}"
    if size == 0:
        return "file is zero bytes"
    try:
        with path.open("rb") as handle:
            handle.read(1)
    except OSError as exc:
        return f"file is not readable: {exc}"
    return None


class Planner:
    """Build a reconciled plan from a job config and a discovered cohort."""

    def __init__(self, telemetry: TelemetrySink, job_id: str | None = None) -> None:
        self._telemetry = telemetry
        self.job_id = job_id or uuid.uuid4().hex[:12]

    def build_plan(self, config: JobConfig) -> Plan:
        """Construct and reconcile the plan for ``config`` over its cohort directory."""
        plan = Plan(
            job_id=self.job_id,
            requested_output=config.requested_output,
            geometry=config.geometry,
            encoders=config.encoders,
            input_dir=config.input_dir,
            output_dir=config.output_dir,
        )

        admissibility = check_admissibility(config.input_dir)
        if admissibility.cohort_block is not None:
            plan.blocked_reason = admissibility.cohort_block
            plan.blocked_detail = admissibility.detail
            self._record_event(
                "cohort-blocked",
                reason=admissibility.cohort_block,
                detail=admissibility.detail,
            )
            return plan

        command = COMMAND_FOR_OUTPUT[config.requested_output]
        stages = STAGES_FOR_OUTPUT[config.requested_output]

        for wsi_path, reason, detail in sorted(admissibility.inadmissible):
            self._add_slide_nodes(plan, config, wsi_path, command, stages, blocked=(reason, detail))
        for wsi_path in sorted(admissibility.admissible):
            self._add_slide_nodes(plan, config, wsi_path, command, stages, blocked=None)

        self._record_event(
            "plan-built",
            detail=(
                f"cohort={len(admissibility.admissible) + len(admissibility.inadmissible)} "
                f"output={config.requested_output.value} nodes={len(plan.nodes)}"
            ),
        )
        return plan

    def _add_slide_nodes(
        self,
        plan: Plan,
        config: JobConfig,
        wsi_path: Path,
        command,
        stages: tuple[Stage, ...],
        blocked: tuple[ReasonCode, str] | None,
    ) -> None:
        stem = wsi_path.stem
        target = TaskTarget(
            slide_stem=stem,
            wsi_path=wsi_path,
            expected_h5_path=patch_h5_path(config.output_dir, stem),
        )
        verdict = None if blocked else self._reconcile_slide(config, target)

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
            if blocked is not None:
                node.decision = Decision.BLOCKED
                node.reason, node.detail = blocked
            else:
                assert verdict is not None
                self._apply_decision(node, stage, config, verdict)
            plan.nodes.append(node)
            prev_node_id = node.node_id

        reason = blocked[0] if blocked else (verdict.reason if verdict else None)
        self._record_event(
            "reconcile",
            slide_stem=stem,
            reason=reason,
            detail=self._slide_decision_summary(plan, stem),
        )

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
        self, node: PlanNode, stage: Stage, config: JobConfig, verdict: Verdict
    ) -> None:
        """Set a node's decision from the slide's reconciliation verdict."""
        requested_output = config.requested_output
        if verdict.valid:
            node.decision = Decision.SKIP
            node.reason = ReasonCode.VALID
            return

        # Geometry conflict against an existing HDF5 → block, with an actionable message
        # (task 4.3), rather than dispatching a run AtlasPatch would reject.
        if verdict.reason is ReasonCode.GEOMETRY_MISMATCH:
            node.decision = Decision.BLOCKED
            node.reason = ReasonCode.GEOMETRY_MISMATCH
            node.detail = (
                f"{verdict.detail}; existing output conflicts with requested geometry "
                f"(patch_size={config.geometry.patch_size}, "
                f"target_mag={config.geometry.target_mag}). "
                "Rerun with --force to overwrite or choose a different output_dir."
            )
            return

        # Coords already valid but features missing/invalid → reuse coords, only embed.
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

    def _slide_decision_summary(self, plan: Plan, stem: str) -> str:
        parts = [f"{n.stage.value}={n.decision.value}" for n in plan.nodes if n.slide_stem == stem]
        return " ".join(parts)

    def _record_event(
        self,
        event: str,
        slide_stem: str | None = None,
        reason: ReasonCode | None = None,
        detail: str = "",
    ) -> None:
        self._telemetry.record_agent_event(
            AgentEventRecord(
                job_id=self.job_id,
                agent=Agent.PLANNER.value,
                event=event,
                slide_stem=slide_stem,
                reason_code=reason.value if reason else None,
                detail=detail,
            )
        )


def discover_cohort(input_dir: Path) -> list[Path]:
    """Return WSI-extension files directly under ``input_dir`` (non-recursive)."""
    directory = Path(input_dir)
    if not directory.is_dir():
        return []
    return sorted(
        p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in WSI_EXTENSIONS
    )
