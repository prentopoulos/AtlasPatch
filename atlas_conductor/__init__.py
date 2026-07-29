"""atlas_conductor — an orchestration layer over the AtlasPatch CLI.

This package coordinates AtlasPatch runs at cohort scale — planning, dispatch,
structural validation, rule-based recovery, and metadata-only telemetry — without
modifying the ML pipeline. It integrates with AtlasPatch through exactly two
documented surfaces: the CLI argv (to run work) and the HDF5 output format at
``<output>/patches/<stem>.h5`` (to verify it). It imports no ``atlas_patch``
internals.

The module-level imports here are intentionally light (standard library only); the
heavy optional dependencies (Google ADK, A2A, BigQuery) live behind the
``atlas-patch[orchestrator]`` extra and are imported lazily by the submodules that
need them, so the core ``atlaspatch`` CLI never imports them.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
