"""Content-addressed, PHI-free data lineage over a run's inputs and outputs (phase 5).

An additive fifth artifact alongside the telemetry families: for each produced output HDF5,
a record tying the SHA-256 of its input WSI(s) + a config fingerprint to the SHA-256 of the
output, keyed on the pseudonymized stem so it correlates with the run's telemetry. See the
``data-lineage`` spec and design D-LIN-1..7.

A :class:`LineageBackend` seam (mirroring real/fake, jsonl/bigquery, in-process/a2a) has a
default credential-free :class:`ManifestLineage` (stdlib only, the CI path) and an opt-in
``DvcLineage`` behind the ``orchestrator`` extra. ``DvcLineage`` is imported lazily by name
(see :func:`atlas_conductor.run.make_lineage_backend`) so importing this package never imports
``dvc``.
"""

from __future__ import annotations

from atlas_conductor.lineage.base import (
    ArtifactPair,
    LineageBackend,
    LineageInput,
    LineagePhiError,
    LineageResult,
    assert_lineage_phi_free,
    build_records,
)
from atlas_conductor.lineage.manifest import ManifestLineage
from atlas_conductor.lineage.records import (
    LineageRecord,
    config_fingerprint,
    sha256_file,
    tool_version,
)
from atlas_conductor.lineage.resolve import (
    LineageResolutionError,
    from_output_dir,
    from_plan,
)

__all__ = [
    "ArtifactPair",
    "LineageBackend",
    "LineageInput",
    "LineagePhiError",
    "LineageRecord",
    "LineageResolutionError",
    "LineageResult",
    "ManifestLineage",
    "assert_lineage_phi_free",
    "build_records",
    "config_fingerprint",
    "from_output_dir",
    "from_plan",
    "sha256_file",
    "tool_version",
]
