"""The ``LineageBackend`` seam and the shared, PHI-gated record builder (D-LIN-1, D-LIN-6).

This mirrors the pattern the repo has proved three times — real/fake adapter, jsonl/bigquery
sink, in-process/a2a transport: one interface, a default credential-free implementation that
is the CI target, and a heavy opt-in implementation behind the ``orchestrator`` extra. Here
the interface is :class:`LineageBackend` and the two implementations are ``ManifestLineage``
(default) and ``DvcLineage`` (opt-in).

Both backends build their records through :func:`build_records` and write them through
:func:`assert_lineage_phi_free`, so they record **identical** hashes and pseudonyms
(the spec requires the DVC backend to match the manifest backend) and inherit the phase-2 PHI
discipline (design D-LIN-6) rather than reimplementing it:

* the slide identifier is the :func:`~atlas_conductor.governance.phi.pseudonymize_stem` token,
  never the raw stem;
* the writer fails closed if a non-pseudonym identifier bearing a HIPAA Safe-Harbor shape ever
  reaches it — the same "reject, don't persist" backstop as :class:`PhiSafeSink`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from atlas_conductor.config import JobConfig
from atlas_conductor.governance.phi import is_pseudonym, pseudonymize_stem, safe_harbor_findings
from atlas_conductor.lineage.records import (
    LineageRecord,
    _utcnow,
    config_fingerprint,
    sha256_file,
    tool_version,
)


class LineagePhiError(ValueError):
    """A lineage record carried an unneutralizable identifier — the write is refused."""


@dataclass(frozen=True)
class ArtifactPair:
    """One produced output HDF5 and the input WSI(s) that fed it, by raw stem.

    ``slide_stem`` is the *raw* stem (which may itself be an identifier); the backend
    pseudonymizes it before it lands in any record or tracked path. ``input_wsis`` is empty
    when no input is resolvable, in which case the record carries an empty input-hash tuple.
    """

    slide_stem: str
    output_h5: Path
    input_wsis: tuple[Path, ...] = ()


@dataclass(frozen=True)
class LineageInput:
    """A finished run to record lineage over (design D-LIN-1, task 2.1)."""

    job_id: str
    output_dir: Path
    config: JobConfig
    artifacts: tuple[ArtifactPair, ...] = ()


@dataclass(frozen=True)
class LineageResult:
    """The outcome of a recording: the records written and where (if anywhere)."""

    backend: str
    records: tuple[LineageRecord, ...] = ()
    manifest_path: Path | None = None
    tracked_paths: tuple[Path, ...] = field(default_factory=tuple)


def assert_lineage_phi_free(record: LineageRecord) -> None:
    """Fail closed if ``record``'s identifier is not a proper pseudonym and looks like PHI.

    The primary control is pseudonymization in :func:`build_records`; this is the backstop
    both backends run before writing. A well-formed ``slide_<hex>`` pseudonym is trusted (and
    deliberately *not* scanned — a random hex run must not trip the digit backstop, mirroring
    :class:`PhiSafeSink` which never scans pseudonyms). Any other stem is treated as free text
    and rejected if it carries a Safe-Harbor identifier shape.
    """
    stem = record.slide_stem
    if is_pseudonym(stem):
        return
    findings = safe_harbor_findings(stem)
    if findings:
        raise LineagePhiError(
            "refusing to write a lineage record whose slide identifier carries a "
            f"Safe-Harbor identifier shape ({', '.join(sorted(findings))}); "
            "the raw stem must be pseudonymized before recording"
        )


def build_records(run: LineageInput) -> list[LineageRecord]:
    """Build the pseudonymized, content-addressed records for ``run`` (D-LIN-2/3/6).

    Shared by both backends so they emit identical hashes and pseudonyms. Each input and
    output is hashed by streaming bytes; the slide is named only by its per-run pseudonym.
    """
    fingerprint = config_fingerprint(run.config)
    version = tool_version()
    recorded_at = _utcnow()
    records: list[LineageRecord] = []
    for artifact in run.artifacts:
        pseudonym = pseudonymize_stem(artifact.slide_stem, run.job_id)
        records.append(
            LineageRecord(
                job_id=run.job_id,
                slide_stem=pseudonym,
                input_sha256=tuple(sha256_file(wsi) for wsi in artifact.input_wsis),
                output_sha256=sha256_file(artifact.output_h5),
                config_fingerprint=fingerprint,
                tool_version=version,
                recorded_at=recorded_at,
            )
        )
    return records


class LineageBackend(ABC):
    """Record content-addressed lineage over a finished run (design D-LIN-1)."""

    #: The backend's selection name (``manifest`` / ``dvc``); set by each subclass.
    name: str

    @abstractmethod
    def record(self, run: LineageInput) -> LineageResult:
        """Record lineage for ``run`` and return the records written and their location."""
