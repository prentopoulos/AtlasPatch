"""The read-only observability surface (phase 3 `add-conductor-gui`, phase 9 React redesign).

Two halves live here. The **producers** — ``reader``, ``model``, ``choreography``,
``messageflow``, ``snapshot``, and ``export`` — read the append-only PHI-free telemetry and
assemble it into the frozen, schema-versioned ``gui-snapshot`` payload (run history, per-slide
structural verdicts, decision trace, cohort metrics, and derived Level-1/Level-2 choreography
state). They import nothing from ``atlas_patch`` and hold no slide pixels or confidence scores.

The **renderer** is the static React SPA whose prebuilt bundle is vendored at ``web_dist/`` and
shipped in the wheel (its source lives at repo-root ``web/``). It consumes one exported
``snapshot.json`` — no Python runtime, no telemetry directory, no server. The ``atlaspatch-conduct
gui`` command serves the bundle over a stdlib HTTP server; the core CLI import graph stays free of
any GUI runtime (enforced by a CI import-guard test).
"""
