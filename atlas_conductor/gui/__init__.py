"""The read-only observability GUI (phase 3 `add-conductor-gui`, design D18).

An additive renderer over the PHI-free telemetry sink: it tails the append-only JSONL
families and renders run history, per-slide verdicts, the decision trace, cohort metrics,
and the Level-1 agent-choreography view. It imports nothing from ``atlas_patch`` and never
renders slide pixels or confidence scores.

Only :mod:`atlas_conductor.gui.app` imports ``streamlit``; the reader, model, and
choreography modules are dependency-free so the report export and the tests can reuse them
without pulling in the GUI runtime (and so the core CLI import graph stays streamlit-free —
enforced by a CI import-guard test).
"""
