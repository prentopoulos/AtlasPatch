"""Pseudonymization and HIPAA Safe-Harbor identifier detection (tasks 1.1; design D20).

Two pure functions, no runtime dependency beyond stdlib:

* :func:`pseudonymize_stem` turns a slide stem — which may itself be an MRN or accession
  number — into a stable, non-reversible token ``slide_<hex>``. The token is a truncated
  HMAC-SHA256 of the stem keyed on a per-run salt derived from the ``job_id``. It is
  therefore *stable within a run* (so a slide's records stay correlatable for the decision
  trace and GUI) but *unlinkable across runs* (a different ``job_id`` yields a different
  token), and not reversible without the salt. This is pseudonymization, not anonymization
  (HIPAA-aligned) — the raw stem never lands in any store.

* :func:`safe_harbor_findings` scans a short operational string for the *shapes* of the
  HIPAA Safe-Harbor identifiers that pseudonymization does not reach — an identifier that
  leaks into a free-text ``detail`` field (for example a raw stderr tail folded into a
  recovery detail). It targets identifier shapes, not narrative de-identification, and is a
  *backstop* to the primary control (pseudonymized stems). Callers fail closed on any hit.
"""

from __future__ import annotations

import hashlib
import hmac
import re

_PSEUDONYM_PREFIX = "slide_"
_PSEUDONYM_HEX_LEN = 16  # 64 bits of the HMAC digest — ample against collision for a cohort


def pseudonymize_stem(stem: str, job_id: str) -> str:
    """Return a stable, non-reversible pseudonym for ``stem`` within the run ``job_id``.

    Deterministic in ``(stem, job_id)``: the same stem in the same run always maps to the
    same token; the same stem in another run (another ``job_id``) maps to a different one.
    """
    salt = hashlib.sha256(f"atlas-conductor::{job_id}".encode()).digest()
    digest = hmac.new(salt, stem.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{_PSEUDONYM_PREFIX}{digest[:_PSEUDONYM_HEX_LEN]}"


def is_pseudonym(value: str) -> bool:
    """True if ``value`` already looks like a :func:`pseudonymize_stem` token."""
    return bool(re.fullmatch(rf"{_PSEUDONYM_PREFIX}[0-9a-f]{{{_PSEUDONYM_HEX_LEN}}}", value))


# HIPAA Safe-Harbor identifier *shapes* in short operational strings. Each pattern is a
# named backstop; matching any one marks the string as carrying an unneutralizable
# identifier. The patterns are deliberately specific so ordinary operational text (batch
# sizes, geometry like ``patch_size=256``, ladder rungs, reason codes) never trips them.
_SAFE_HARBOR_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("phone", re.compile(r"\b\d{3}[.\-)]\s?\d{3}[.\-]\d{4}\b")),
    # MRN / accession stated with an explicit label, e.g. "MRN: 00123" or "accession A12345".
    ("mrn", re.compile(r"\b(?:mrn|accession|acc|patient[ _-]?id)\b[:#]?\s*[A-Za-z]?\d{3,}", re.I)),
    # A bare long digit run (>= 7 digits) is almost never operational metadata but is the
    # shape of an MRN / accession / device id — fail closed on it.
    ("long-digit-run", re.compile(r"\b\d{7,}\b")),
    # A full date (finer than a year) — Safe-Harbor allows year only.
    ("date", re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b")),
    ("ipv4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("url-with-host", re.compile(r"\bhttps?://[\w.-]+", re.I)),
)


def safe_harbor_findings(text: str) -> list[str]:
    """Return the names of every Safe-Harbor identifier shape found in ``text``.

    Empty list means the string carries no detectable identifier. A non-empty list is the
    signal to reject (fail closed); its contents name the *shapes* found (never the matched
    identifier value, which must not be re-logged).
    """
    if not text:
        return []
    return [name for name, pattern in _SAFE_HARBOR_PATTERNS if pattern.search(text)]
