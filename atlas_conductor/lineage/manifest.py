"""The default, credential-free manifest lineage backend (D-LIN-1, task 2.2).

``ManifestLineage`` uses only the Python standard library — ``hashlib`` (via
:mod:`atlas_conductor.lineage.records`) and ``json`` — so it needs no DVC, no network, and no
credentials, and is the path exercised in CI. It appends one JSON line per produced output to
``<output_dir>/lineage/manifest.jsonl`` (sibling to ``telemetry/``), each line a
content-addressed :class:`~atlas_conductor.lineage.records.LineageRecord`. Every record is run
through :func:`assert_lineage_phi_free` before it is written, so a leaked identifier fails
closed rather than landing in the manifest.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict
from pathlib import Path

from atlas_conductor.lineage.base import (
    LineageBackend,
    LineageInput,
    LineageResult,
    assert_lineage_phi_free,
    build_records,
)

MANIFEST_RELATIVE_PATH = Path("lineage") / "manifest.jsonl"


class ManifestLineage(LineageBackend):
    """Append content-addressed lineage records to a JSON manifest (stdlib only)."""

    name = "manifest"

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def record(self, run: LineageInput) -> LineageResult:
        records = build_records(run)
        manifest_path = Path(run.output_dir) / MANIFEST_RELATIVE_PATH
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, manifest_path.open("a", encoding="utf-8") as handle:
            for record in records:
                assert_lineage_phi_free(record)  # fail closed before the line is written
                handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")
        return LineageResult(
            backend=self.name,
            records=tuple(records),
            manifest_path=manifest_path,
        )
