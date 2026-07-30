"""The machine-checkable control register (design D-CMP-1).

``controls.yaml`` holds the obligation→control→evidence rows the compliance dossier renders
from. Keeping one *structured* source of truth — rather than free prose — is what lets CI
resolve every citation and prove the dossier has not drifted from the code (design D-CMP-2);
it is the Model Card's drift-check discipline (D24) generalized from one card to the whole
obligation map. YAML is used because PyYAML is already a phase-1 runtime dependency; a
JSON register with the same schema parses through the same loader with no code change.

Each :class:`ControlRow` is frozen and every field is required to be populated — a row that
cites nothing, or an obligation with no control, is exactly the empty claim the register
exists to forbid, so :func:`load_registry` rejects it loudly at parse time.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# The frameworks the register maps against. Kept small and closed so a typo in a row's
# ``framework`` fails the parse rather than silently creating a third bucket in the dossier.
FRAMEWORKS = ("eu-ai-act", "iso-42001")

_REQUIRED_FIELDS = (
    "id",
    "framework",
    "clause",
    "obligation",
    "control",
    "evidence_module",
    "evidence_test",
)


class RegistryError(ValueError):
    """The control register is malformed — a missing field, unknown framework, or bad shape."""


@dataclass(frozen=True)
class ControlRow:
    """One obligation→control→evidence mapping in the register.

    ``evidence_module`` is a repo-relative module path (e.g.
    ``atlas_conductor/governance/audit.py``) and ``evidence_test`` is a pytest node id
    (``tests/...::test_name``); the CI check (design D-CMP-2) resolves both to something that
    exists in the repository.
    """

    id: str
    framework: str
    clause: str
    obligation: str
    control: str
    evidence_module: str
    evidence_test: str

    def to_dict(self) -> dict[str, str]:
        return {field: getattr(self, field) for field in _REQUIRED_FIELDS}


def default_registry_path() -> Path:
    """The shipped register bundled beside this module (``controls.yaml``)."""
    return Path(__file__).resolve().parent / "controls.yaml"


def _load_raw(path: Path) -> Any:
    """Parse the register file as YAML, falling back to JSON if PyYAML is unavailable."""
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore[import-untyped]
    except ModuleNotFoundError:
        # The same schema serializes to JSON with zero dependencies (design D-CMP-1).
        return json.loads(text)
    return yaml.safe_load(text)


def _row_from_mapping(raw: Any, index: int) -> ControlRow:
    if not isinstance(raw, dict):
        raise RegistryError(f"control row {index} is not a mapping (got {type(raw).__name__})")
    missing = [field for field in _REQUIRED_FIELDS if not str(raw.get(field, "")).strip()]
    if missing:
        row_id = raw.get("id", f"#{index}")
        raise RegistryError(f"control row {row_id!r} is missing field(s): {', '.join(missing)}")
    if raw["framework"] not in FRAMEWORKS:
        raise RegistryError(
            f"control row {raw['id']!r} has unknown framework {raw['framework']!r} "
            f"(expected one of {', '.join(FRAMEWORKS)})"
        )
    return ControlRow(**{field: str(raw[field]).strip() for field in _REQUIRED_FIELDS})


def load_registry(path: str | Path | None = None) -> list[ControlRow]:
    """Parse the control register into rows, validating every row is fully populated.

    ``path`` defaults to the shipped :func:`default_registry_path`. The parsed document must
    be a list of mappings (or a ``{"controls": [...]}`` wrapper); every row must carry all
    seven fields, name a known framework, and every ``id`` must be unique.
    """
    registry_path = Path(path) if path is not None else default_registry_path()
    if not registry_path.is_file():
        raise RegistryError(f"control register not found: {registry_path}")

    raw = _load_raw(registry_path)
    if isinstance(raw, dict) and "controls" in raw:
        raw = raw["controls"]
    if not isinstance(raw, list) or not raw:
        raise RegistryError("control register must be a non-empty list of control rows")

    rows = [_row_from_mapping(item, index) for index, item in enumerate(raw)]
    seen: set[str] = set()
    for row in rows:
        if row.id in seen:
            raise RegistryError(f"duplicate control id {row.id!r} in the register")
        seen.add(row.id)
    return rows
