"""The recovery agent (slice A3).

This submodule exists from slice A1 to fix the package shape (task 1.1), but its
behavior lands in slice A3: two-source failure classification into the bounded
taxonomy (``resource-transient`` / ``precondition-block`` / ``input-data`` /
``structural-invalid`` / ``dependency-blocked`` / ``unknown``), the monotone recovery
action ladder over the CLI's tuning knobs (design D7), ``unknown → block`` (never
blind-retry), and downstream dependency-blocking. Recovery *proposes* classifications
and plan-deltas; the planner integrates them as the single writer of plan state
(design D6). The relevant enums (:class:`~atlas_conductor.contracts.Classification`,
:class:`~atlas_conductor.contracts.RecoveryAction`) are already defined in
``contracts`` so the telemetry recovery-outcome fields are in place from A1.
"""

from __future__ import annotations
