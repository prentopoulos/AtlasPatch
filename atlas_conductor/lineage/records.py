"""The lineage data model: a content-addressed record plus its hashing primitives (D-LIN-2, D-LIN-3).

A :class:`LineageRecord` ties **which exact input bytes plus which config produced which
output HDF5** together for one produced artifact. Like the telemetry records (design D9) it
is a frozen dataclass of scalars/strings — SHA-256 hex digests, a config fingerprint, a
version string, and identifiers — with no field able to hold a WSI image, a tissue mask, or
an embedding matrix. The metadata-only, no-pixel invariant therefore holds *by type*: hashes
stand in for the data (D-LIN-5), and nothing here can carry the data itself.

Hashing (:func:`sha256_file`) streams file bytes in fixed chunks and treats every WSI and
HDF5 as an opaque blob — the layer never parses slide content or interprets the HDF5 schema,
preserving the operational-not-clinical invariant and avoiding any ``atlas_patch`` import
(D-LIN-3). The tool version (:func:`tool_version`) is read from installed distribution
metadata, again without importing the ML package (D-LIN-2, task 1.3).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from atlas_conductor.config import JobConfig

_CHUNK_BYTES = 1 << 20  # 1 MiB streaming chunks — hashing is I/O-bound, not memory-bound
_FINGERPRINT_HEX_LEN = 16  # 64 bits of the config digest — ample to detect any config edit
_DISTRIBUTION_NAME = "atlas-patch"
_UNKNOWN_VERSION = "unknown"


@dataclass(frozen=True)
class LineageRecord:
    """One content-addressed provenance record for a single produced output HDF5.

    ``slide_stem`` is the PHI-free pseudonym (never the raw stem). ``input_sha256`` is a
    tuple of the SHA-256 of each input WSI feeding the slide — empty when no input is
    resolvable (D-LIN, "Telemetry may not name every input↔output pair"). Every field is a
    scalar or a tuple of hex strings; none can hold an array.
    """

    job_id: str
    slide_stem: str  # pseudonym (slide_<hex>), correlates with the run's telemetry
    input_sha256: tuple[str, ...]
    output_sha256: str
    config_fingerprint: str
    tool_version: str
    recorded_at: str = ""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: str | Path) -> str:
    """Return the hex SHA-256 of ``path``'s bytes, streamed in fixed chunks.

    The file is treated as an opaque blob — no HDF5/WSI semantics are read (D-LIN-3) — so
    a WSI and an HDF5 hash the same way and neither is loaded into memory whole.
    """
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def config_fingerprint(config: JobConfig) -> str:
    """A short deterministic hash of the run's *config identity* (D-LIN-2).

    Hashes ``(patch_size, target_mag, step_size, sorted(encoders), requested_output)`` using
    the same geometry encoding :func:`~atlas_conductor.contracts.make_idempotency_key` uses,
    so a config edit that changes geometry changes the fingerprint exactly as it changes the
    idempotency key. It is run-independent (no ``job_id``/stem), so the same config reproduces
    the same fingerprint, and a geometry or encoder change produces a detectably different one.
    """
    geo = config.geometry
    parts = "::".join(
        [
            f"ps{geo.patch_size}-mag{geo.target_mag}-ss{geo.step_size}",
            "enc:" + ",".join(sorted(config.encoders)),
            f"out:{config.requested_output.value}",
        ]
    )
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()[:_FINGERPRINT_HEX_LEN]


def tool_version() -> str:
    """Resolve the installed ``atlas-patch`` version from distribution metadata (task 1.3).

    Uses :mod:`importlib.metadata` rather than importing ``atlas_patch`` (which would pull the
    ML dependency graph). Returns ``"unknown"`` when the distribution metadata is absent (for
    example an un-installed source checkout), so lineage recording never fails on version lookup.
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(_DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return _UNKNOWN_VERSION
