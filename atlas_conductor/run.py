"""The run orchestration façade — composes plan → dispatch → validate → report.

This is the single in-process coordinator of the four logical components (design D8):
the planner builds a reconciled plan, the scheduler dispatches the first pass and
accounts per slide via the validator, and the report renders the outcome. Wiring the
components as A2A peers is phase 4; here they are plain typed calls.

The façade is also where the phase-2 governance gates are *installed* (design D19/D21):
the configured telemetry sink is wrapped once in a :class:`PhiSafeSink` so every component
writes through the PHI-free gate transparently, and the human-in-the-loop confirmer is
selected from ``JobConfig.unattended``. Both are additive — the underlying phase-1 sink and
scheduler behave identically when unwrapped.

``plan_job`` exposes the planner on its own so ``--dry-run`` (task 4.5) can render the
reconciled plan without any dispatch.
"""

from __future__ import annotations

import logging

from atlas_conductor.classifier import FailureClassifier, RuleClassifier
from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import Plan
from atlas_conductor.dispatch import ExecutionAdapter, FakeAdapter, RealAdapter
from atlas_conductor.governance import AuditTrail, Confirmer, PhiSafeSink, default_confirmer
from atlas_conductor.lineage.base import LineageBackend
from atlas_conductor.planning import Planner
from atlas_conductor.scheduler import RunResult, Scheduler
from atlas_conductor.telemetry import JsonlTelemetrySink, TelemetrySink
from atlas_conductor.transport import AgentTransport, make_transport

logger = logging.getLogger(__name__)


def make_adapter(name: str) -> tuple[ExecutionAdapter, str]:
    """Resolve an adapter by name. ``fake`` needs no GPU; ``real`` drives the CLI."""
    if name == "fake":
        return FakeAdapter(), "fake"
    if name == "real":
        return RealAdapter(), "real"
    raise ValueError(f"unknown adapter {name!r}; choose 'fake' or 'real'")


def make_telemetry_sink(config: JobConfig, jsonl_dir: str) -> TelemetrySink:
    """Resolve the telemetry backend from ``config`` (design D-DIST-4).

    ``jsonl`` (the default) appends to ``jsonl_dir`` and needs no cloud; ``bigquery`` is
    opt-in and requires the ``orchestrator`` extra (its client is imported behind a guard
    inside :class:`~atlas_conductor.telemetry_bigquery.BigQueryTelemetrySink`).
    """
    if config.telemetry_backend == "bigquery":
        from atlas_conductor.telemetry_bigquery import BigQueryTelemetrySink

        assert config.telemetry_dataset is not None  # enforced by config validation
        return BigQueryTelemetrySink(config.telemetry_dataset)
    return JsonlTelemetrySink(jsonl_dir)


def make_lineage_backend(name: str) -> LineageBackend:
    """Resolve a lineage backend by name (design D-LIN-1), mirroring ``make_adapter``.

    ``manifest`` (the default) is stdlib-only and credential-free; ``dvc`` is opt-in and needs
    the ``orchestrator`` extra — its module (and therefore ``dvc``) is imported behind this
    guard, never at import time, so the core CLI import graph stays DVC-free.
    """
    if name == "manifest":
        from atlas_conductor.lineage.manifest import ManifestLineage

        return ManifestLineage()
    if name == "dvc":
        from atlas_conductor.lineage.dvc_backend import DvcLineage

        return DvcLineage()
    raise ValueError(f"unknown lineage backend {name!r}; choose 'manifest' or 'dvc'")


def make_classifier(config: JobConfig) -> FailureClassifier:
    """Resolve the recovery classifier from ``config`` (design D-LRC-6), mirroring ``make_adapter``.

    ``rule`` (the default) returns the hand-written rules, keeping a default run byte-for-byte
    identical. ``learned`` loads the JSON model artifact and wraps it in a
    :class:`~atlas_conductor.classifier.learned.LearnedClassifier` over a rule fallback. A
    missing, unreadable, or ``feature_version``-mismatched model logs and falls back to the
    rules rather than failing the run — the numpy model is imported only on this opt-in path.
    """
    if config.classifier_backend != "learned":
        return RuleClassifier()

    from atlas_conductor.classifier.learned import LearnedClassifier
    from atlas_conductor.classifier.model import LinearModel

    path = config.classifier_model_path
    if not path:
        logger.warning("classifier backend 'learned' selected but no model_path set; using rules")
        return RuleClassifier()
    try:
        model = LinearModel.load(path)
    except (OSError, ValueError) as exc:
        # FileNotFoundError/OSError (missing/unreadable), JSONDecodeError/FeatureVersionMismatch
        # (both ValueError) — degrade to the rules rather than failing the run.
        logger.warning("could not load learned model %r (%s); falling back to rules", path, exc)
        return RuleClassifier()
    return LearnedClassifier(
        model,
        fallback=RuleClassifier(),
        threshold=config.classifier_confidence_threshold,
    )


def plan_job(config: JobConfig, telemetry: TelemetrySink, audit: AuditTrail | None = None) -> Plan:
    """Build and reconcile the plan for ``config`` without dispatching anything."""
    return Planner(PhiSafeSink(telemetry, audit=audit)).build_plan(config)


def run_job(
    config: JobConfig,
    telemetry: TelemetrySink,
    adapter: ExecutionAdapter | None = None,
    adapter_name: str = "fake",
    audit: AuditTrail | None = None,
    confirmer: Confirmer | None = None,
    transport: AgentTransport | None = None,
    classifier: FailureClassifier | None = None,
) -> RunResult:
    """Plan and execute one job, returning the per-slide run result.

    ``adapter`` defaults to the :class:`FakeAdapter` so the full loop runs with no GPU
    and no real slides (execution-dispatch spec). Pass the real adapter to drive the
    AtlasPatch CLI as a subprocess.

    The configured ``telemetry`` sink is wrapped in a :class:`PhiSafeSink` (design D12), and
    the HITL confirmer defaults to the policy for ``config.unattended`` — hold irreversible
    actions when attended, waive (and record the waiver) when unattended (design D13).
    ``audit`` is the tamper-evident trail consequential actions are appended to.

    ``transport`` routes the four inter-agent handoffs (design D-DIST-2); it defaults to the
    one named by ``config.transport`` (in-process unless the config opts into ``a2a``),
    built over the same gated sink so its ``message_flow`` rows are PHI-free too. Passing an
    explicit transport (e.g. a stubbed A2A transport) overrides the config selection.

    ``classifier`` selects the recovery classifier (design D-LRC-6); it defaults to the one
    named by ``config.classifier_backend`` (``rule`` unless the config opts into ``learned``).
    The default rule path keeps a default run byte-for-byte identical to pre-seam recovery.
    """
    if adapter is None:
        adapter = FakeAdapter()
    gated = PhiSafeSink(telemetry, audit=audit)
    if confirmer is None:
        confirmer = default_confirmer(config.unattended)
    if classifier is None:
        classifier = make_classifier(config)
    plan = Planner(gated).build_plan(config)
    if transport is None:
        transport = make_transport(config.transport, gated, plan.job_id)
    scheduler = Scheduler(
        config,
        adapter,
        gated,
        adapter_name=adapter_name,
        audit=audit,
        confirmer=confirmer,
        transport=transport,
        classifier=classifier,
    )
    result = scheduler.run(plan)
    _record_lineage(config, plan)
    return result


def _record_lineage(config: JobConfig, plan: Plan) -> None:
    """Record lineage over the finished run's outputs when the config opts in (design D-LIN-7).

    Invoked strictly *after* the scheduler returns and writes only a new sibling artifact, so
    enabling it cannot change any plan/dispatch/validation/recovery/telemetry result. Off (a
    no-op) unless ``config.lineage_backend`` is set.
    """
    if config.lineage_backend is None:
        return
    from atlas_conductor.lineage.resolve import from_plan

    backend = make_lineage_backend(config.lineage_backend)
    backend.record(from_plan(plan, config))
