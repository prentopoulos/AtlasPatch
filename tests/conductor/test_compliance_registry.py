"""The shipped control register parses and every row is fully populated (task 1.1).

The register (design D-CMP-1) is the single source of truth the dossier renders from and CI
resolves citations against, so a malformed or half-filled row is a defect, not a warning:
:func:`load_registry` must reject it and the shipped register must survive that rejection.
"""

from __future__ import annotations

import pytest

from atlas_conductor.compliance.registry import (
    FRAMEWORKS,
    RegistryError,
    default_registry_path,
    load_registry,
)


def test_shipped_register_parses_and_every_row_is_populated() -> None:
    rows = load_registry()
    assert rows, "the shipped control register must contain control rows"
    ids = [row.id for row in rows]
    assert len(ids) == len(set(ids)), "control ids must be unique"
    for row in rows:
        assert row.framework in FRAMEWORKS
        # Every field is required to be a non-empty value.
        for field, value in row.to_dict().items():
            assert value.strip(), f"row {row.id} has empty field {field}"


def test_default_registry_path_points_at_a_bundled_file() -> None:
    assert default_registry_path().is_file()


def test_a_row_missing_a_field_is_rejected(tmp_path) -> None:
    bad = tmp_path / "controls.yaml"
    bad.write_text(
        "controls:\n"
        "  - id: X-1\n"
        "    framework: eu-ai-act\n"
        "    clause: c\n"
        "    obligation: o\n"
        "    control: k\n"
        "    evidence_module: m\n",
        # evidence_test intentionally omitted
        encoding="utf-8",
    )
    with pytest.raises(RegistryError):
        load_registry(bad)


def test_an_unknown_framework_is_rejected(tmp_path) -> None:
    bad = tmp_path / "controls.yaml"
    bad.write_text(
        "controls:\n"
        "  - id: X-1\n"
        "    framework: not-a-framework\n"
        "    clause: c\n"
        "    obligation: o\n"
        "    control: k\n"
        "    evidence_module: m\n"
        "    evidence_test: t\n",
        encoding="utf-8",
    )
    with pytest.raises(RegistryError):
        load_registry(bad)
