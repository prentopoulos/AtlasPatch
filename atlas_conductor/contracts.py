"""The declarative data model shared by every conductor component (tasks 2.1–2.3).

These types are the seam the whole layer is built on. Per design D10 the task
contract is *adapter-agnostic*: it carries logical intent (stage, targets with
expected HDF5 paths, geometry, encoders, tuning, attempt/mutation history,
dependencies, an idempotency key) and never a pre-baked CLI argv (real-adapter
specific) or a fixture directive (fake-adapter specific). Each adapter translates a
task into its own action.

Per design D17 these shapes must be correct in slice A1 because every later run —
planner decisions, the decision trace, the GUI, the phase-2 PHI gate — renders or
gates off them. The enums therefore enumerate the full taxonomies now (recovery
classifications, actions) even though slices A2/A3 are what exercise them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Stage(str, Enum):
    """A logical pipeline stage. The plan is a DAG of these (design D1)."""

    SEGMENT = "segment"
    EMBED = "embed"


class RequestedOutput(str, Enum):
    """What a job asks for. Determines the command and the meaning of 'valid'."""

    COORDS = "coords"
    FEATURES = "features"


class Command(str, Enum):
    """An AtlasPatch CLI command. Stages map onto these (stage→command, design D1)."""

    SEGMENT_AND_GET_COORDS = "segment-and-get-coords"
    PROCESS = "process"


class Decision(str, Enum):
    """A planner's per-node reconciliation decision (design D4)."""

    SKIP = "skip"  # requested output already present and structurally valid
    RUN = "run"  # must be executed
    REUSE = "reuse"  # coords valid, only the embed stage needs running
    BLOCKED = "blocked"  # cannot run (geometry conflict, bad input, failed upstream)


class ReasonCode(str, Enum):
    """Why a verdict/decision was reached — the vocabulary of the decision trace.

    Validation reason codes distinguish the structural failure modes (design D3/3.2);
    admissibility and block codes cover plan-time rejections (design D16); ``VALID`` is
    the success case.
    """

    # validation outcomes
    VALID = "valid"
    MISSING = "missing"  # expected HDF5 absent
    CORRUPT = "corrupt"  # present but does not open / not a valid HDF5
    NO_COORDS = "no-coords"  # coords dataset missing / wrong shape / empty
    MISSING_ATTRS = "missing-attrs"  # required geometry attrs absent
    GEOMETRY_MISMATCH = "geometry-mismatch"  # attrs present but differ from requested
    MISSING_FEATURES = "missing-features"  # requested features/<enc> absent
    ROW_MISMATCH = "row-mismatch"  # feature rows != coord rows
    NAN_FEATURES = "nan-features"  # feature dataset contains NaN
    # plan-time admissibility (design D16, slice A2)
    EMPTY_COHORT = "empty-cohort"
    NO_WSI_FILES = "no-wsi-files"
    UNREADABLE_INPUT = "unreadable-input"
    # coordination / recovery outcomes
    DEPENDENCY_BLOCKED = "dependency-blocked"
    ATTEMPTS_EXHAUSTED = "attempts-exhausted"
    PRECONDITION_BLOCK = "precondition-block"
    UNKNOWN_FAILURE = "unknown-failure"
    # governance (phase 2): an irreversible action is held pending human confirmation
    # (design D13/D21). Additive; only set by the HITL gate when an action is not applied.
    AWAITING_CONFIRMATION = "awaiting-confirmation"


class SlideOutcome(str, Enum):
    """A slide's terminal outcome in the summary report (task 8.2)."""

    VALID = "valid"
    SKIPPED = "skipped"
    QUARANTINED = "quarantined"
    BLOCKED = "blocked"


class Classification(str, Enum):
    """The bounded failure taxonomy (failure-recovery spec; slice A3)."""

    RESOURCE_TRANSIENT = "resource-transient"
    PRECONDITION_BLOCK = "precondition-block"
    INPUT_DATA = "input-data"
    STRUCTURAL_INVALID = "structural-invalid"
    DEPENDENCY_BLOCKED = "dependency-blocked"
    UNKNOWN = "unknown"


class RecoveryAction(str, Enum):
    """The bounded recovery action set — exactly the CLI's tuning knobs (design D7)."""

    RETRY_AS_IS = "retry_as_is"
    RETRY_WITH_MUTATION = "retry_with_mutation"
    FORCE_REPROCESS = "force_reprocess"
    QUARANTINE_ITEM = "quarantine_item"
    BLOCK_ITEM = "block_item"
    BLOCK_JOB = "block_job"
    MARK_DEPENDENTS_BLOCKED = "mark_dependents_blocked"


# The stages required to satisfy each requested output, and the CLI command a stage
# dispatches onto (design D1). ``process`` covers both stages; ``segment-and-get-coords``
# covers segmentation only.
STAGES_FOR_OUTPUT: dict[RequestedOutput, tuple[Stage, ...]] = {
    RequestedOutput.COORDS: (Stage.SEGMENT,),
    RequestedOutput.FEATURES: (Stage.SEGMENT, Stage.EMBED),
}
COMMAND_FOR_OUTPUT: dict[RequestedOutput, Command] = {
    RequestedOutput.COORDS: Command.SEGMENT_AND_GET_COORDS,
    RequestedOutput.FEATURES: Command.PROCESS,
}


@dataclass(frozen=True)
class Geometry:
    """Patch geometry — the identity that must match an existing HDF5's attrs."""

    patch_size: int
    target_mag: int
    step_size: int | None = None


@dataclass(frozen=True)
class Tuning:
    """CLI tuning knobs a recovery mutation may adjust (design D7).

    ``None`` means "leave at the CLI default". Slice A1 always carries defaults; the
    A3 recovery ladder produces mutated copies with monotonically smaller values.
    """

    feature_batch_size: int | None = None
    seg_batch_size: int | None = None
    max_open_slides: int | None = None
    patch_workers: int | None = None
    feature_precision: str | None = None
    force: bool = False


@dataclass(frozen=True)
class TaskTarget:
    """One slide within a task, with the HDF5 path its output is verified at."""

    slide_stem: str
    wsi_path: Path
    expected_h5_path: Path


@dataclass(frozen=True)
class Task:
    """A unit of work handed to an adapter (task 2.2; design D10).

    Declarative intent only — no argv, no fixture directive. ``input_path`` is a
    directory for a cohort first pass or a single file for a per-file recovery retry
    (design D2); ``targets`` is the per-slide accounting unit regardless.
    """

    stage: Stage
    command: Command
    requested_output: RequestedOutput
    input_path: Path
    output_dir: Path
    targets: tuple[TaskTarget, ...]
    geometry: Geometry
    encoders: tuple[str, ...] = ()
    tuning: Tuning = field(default_factory=Tuning)
    attempt: int = 1
    mutation_history: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    idempotency_key: str = ""


@dataclass(frozen=True)
class Outcome:
    """The raw, unclassified result of an invocation (task 2.3).

    The worker forwards this as-is (execution-dispatch spec); classification is the
    recovery agent's job. Carries no arrays — only scalars and short text tails.
    """

    exit_code: int
    stdout_tail: str = ""
    stderr_tail: str = ""
    duration_s: float = 0.0
    produced_paths: tuple[Path, ...] = ()
    # Ground-truth label when produced by the fake adapter's injection (design D14);
    # ``None`` for the real adapter. Lets CI measure classifier accuracy vs truth.
    injected_label: str | None = None


@dataclass(frozen=True)
class Verdict:
    """A structural-validity verdict for one slide's requested output (task 3.1)."""

    valid: bool
    reason: ReasonCode
    detail: str = ""


@dataclass
class PlanNode:
    """One (slide, stage) node in the plan DAG (task 2.1).

    The planner is the single writer of ``decision``/``reason``/``attempts`` (design
    D6). ``dependencies`` holds the ids of upstream nodes that must be satisfied
    before this node may be scheduled.
    """

    node_id: str
    slide_stem: str
    stage: Stage
    command: Command
    target: TaskTarget
    decision: Decision = Decision.RUN
    reason: ReasonCode | None = None
    detail: str = ""
    dependencies: tuple[str, ...] = ()
    attempt_budget: int = 3
    attempts: int = 0
    # Recovery state, written only by the planner (design D6): the current tuning to
    # dispatch with, and the ordered history of applied recovery mutations (design D14).
    tuning: Tuning = field(default_factory=Tuning)
    mutation_history: tuple[str, ...] = ()


@dataclass
class Plan:
    """The reconciled DAG for a whole cohort (task 2.1)."""

    job_id: str
    requested_output: RequestedOutput
    geometry: Geometry
    encoders: tuple[str, ...]
    input_dir: Path
    output_dir: Path
    nodes: list[PlanNode] = field(default_factory=list)
    # A cohort-level admissibility block (design D16); set only when the whole cohort
    # is rejected before dispatch.
    blocked_reason: ReasonCode | None = None
    blocked_detail: str = ""

    @property
    def is_blocked(self) -> bool:
        return self.blocked_reason is not None

    def nodes_for(self, stage: Stage) -> list[PlanNode]:
        return [n for n in self.nodes if n.stage == stage]

    def runnable_nodes(self, stage: Stage) -> list[PlanNode]:
        """Nodes at ``stage`` whose decision means they should be dispatched."""
        return [
            n
            for n in self.nodes
            if n.stage == stage and n.decision in (Decision.RUN, Decision.REUSE)
        ]

    def slide_stems(self) -> list[str]:
        seen: dict[str, None] = {}
        for node in self.nodes:
            seen.setdefault(node.slide_stem, None)
        return list(seen)


def make_idempotency_key(
    job_id: str, slide_stem: str, stage: Stage, geometry: Geometry, encoder: str = ""
) -> str:
    """Compose the resume-safe idempotency key (design open question).

    Keyed on ``(job_id, slide_stem, stage, geometry, encoder)`` so that a config edit
    that changes geometry yields a distinct key and does not silently reuse work.
    """
    geo = f"ps{geometry.patch_size}-mag{geometry.target_mag}-ss{geometry.step_size}"
    return "::".join([job_id, slide_stem, stage.value, geo, encoder])
