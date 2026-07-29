"""Tamper-evident, append-only audit trail (tasks 4.1; design D22).

The audit trail records every *consequential* action — each dispatch, each recovery
decision, each human-in-the-loop hold / approve / waive, and each PHI-gate rejection —
in a hash chain: every entry carries the hash of its predecessor plus a hash over its own
canonical payload, so any post-hoc edit, reordering, or deletion breaks the chain and is
detectable by :func:`verify_audit_chain`. This is tamper-*evidence* (stdlib ``hashlib``
only), not tamper-*proofing* (WORM storage / signing are out of scope, design Non-Goals).

The trail is a *sibling* of telemetry, not a fifth telemetry family (design D22): keeping
the chaining out of the append-only telemetry families leaves their reconstruction/readback
path — and the phase-4 BigQuery schema — uncomplicated, and makes integrity independently
verifiable. Audit payloads are expected to already be PHI-safe (the caller pseudonymizes
stems and omits identifiers), so the trail cannot become a PHI side channel.
"""

from __future__ import annotations

import hashlib
import json
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# The genesis predecessor hash — a fixed anchor the first real entry chains onto.
GENESIS_HASH = "0" * 64

# Audit payloads carry operational metadata only — never a pixel, mask, or embedding. The
# no-array guarantee is enforced by construction: a payload value must be a JSON scalar.
_SCALAR_TYPES = (str, int, float, bool, type(None))


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(payload: dict[str, Any]) -> str:
    """A stable serialization so the same payload always hashes identically."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def entry_hash(prev_hash: str, action: str, timestamp: str, payload: dict[str, Any]) -> str:
    """The hash linking one entry to its predecessor (chain step)."""
    material = f"{prev_hash}\n{action}\n{timestamp}\n{_canonical(payload)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuditEntry:
    """One link in the audit chain."""

    action: str
    timestamp: str
    payload: dict[str, Any]
    prev_hash: str
    entry_hash: str

    def to_row(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
        }


class AuditTrail(ABC):
    """Append-only, hash-chained audit sink."""

    @abstractmethod
    def append(self, action: str, payload: dict[str, Any]) -> AuditEntry:
        """Append a consequential action, chaining it onto the current head."""

    @abstractmethod
    def entries(self) -> list[dict[str, Any]]:
        """Read the trail back as ordered rows (for verification / inspection)."""

    def _make_entry(self, prev_hash: str, action: str, payload: dict[str, Any]) -> AuditEntry:
        for key, value in payload.items():
            if not isinstance(value, _SCALAR_TYPES):
                raise TypeError(
                    f"audit payload field {key!r} must be a scalar (no array can be "
                    f"recorded), got {type(value).__name__}"
                )
        timestamp = _utcnow()
        return AuditEntry(
            action=action,
            timestamp=timestamp,
            payload=payload,
            prev_hash=prev_hash,
            entry_hash=entry_hash(prev_hash, action, timestamp, payload),
        )


class InMemoryAuditTrail(AuditTrail):
    """A trail kept in a list — convenient for tests and assertions."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []
        self._lock = threading.Lock()

    def append(self, action: str, payload: dict[str, Any]) -> AuditEntry:
        with self._lock:
            prev = self._entries[-1].entry_hash if self._entries else GENESIS_HASH
            entry = self._make_entry(prev, action, payload)
            self._entries.append(entry)
            return entry

    def entries(self) -> list[dict[str, Any]]:
        return [e.to_row() for e in self._entries]


class JsonlAuditTrail(AuditTrail):
    """A trail persisted as an append-only ``audit.jsonl`` hash chain."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(self, action: str, payload: dict[str, Any]) -> AuditEntry:
        with self._lock:
            rows = self._read_rows()
            prev = rows[-1]["entry_hash"] if rows else GENESIS_HASH
            entry = self._make_entry(prev, action, payload)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry.to_row(), sort_keys=True) + "\n")
            return entry

    def _read_rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def entries(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._read_rows()


@dataclass(frozen=True)
class ChainVerification:
    """The result of walking an audit trail's hash chain."""

    intact: bool
    broken_index: int | None = None  # 0-based index of the first bad entry, if any
    detail: str = ""


def verify_audit_chain(entries: list[dict[str, Any]]) -> ChainVerification:
    """Walk ``entries`` and report whether the hash chain is intact.

    Detects an edited entry (its recomputed hash no longer matches), a deletion or
    reordering (an entry's ``prev_hash`` no longer equals its predecessor's ``entry_hash``),
    and a broken anchor (the first entry must chain onto :data:`GENESIS_HASH`).
    """
    prev = GENESIS_HASH
    for index, row in enumerate(entries):
        if row.get("prev_hash") != prev:
            return ChainVerification(
                False, index, f"entry {index} prev_hash does not match the chain head"
            )
        recomputed = entry_hash(row["prev_hash"], row["action"], row["timestamp"], row["payload"])
        if recomputed != row.get("entry_hash"):
            return ChainVerification(
                False, index, f"entry {index} content does not match its recorded hash"
            )
        prev = row["entry_hash"]
    return ChainVerification(True)
