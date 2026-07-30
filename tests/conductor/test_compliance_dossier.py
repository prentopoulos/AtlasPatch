"""CI drift + traceability check for the compliance dossier (task 3.2; design D-CMP-2).

Proves the shipped register and ``COMPLIANCE.md`` are in lockstep — every cited module/test
resolves, no placeholder remains, every register row appears in the dossier — and that each
failure mode the check exists to catch actually fails it.
"""

from __future__ import annotations

from pathlib import Path

import atlas_conductor
from atlas_conductor.compliance.check import check_compliance
from atlas_conductor.compliance.registry import default_registry_path

_REPO_ROOT = Path(atlas_conductor.__file__).resolve().parent.parent
_DOSSIER = _REPO_ROOT / "COMPLIANCE.md"


def test_shipped_dossier_and_register_are_in_sync() -> None:
    result = check_compliance(None, _DOSSIER, _REPO_ROOT)
    result.raise_if_failed()
    assert result.ok


def test_a_citation_to_a_missing_module_fails(tmp_path: Path) -> None:
    registry = tmp_path / "controls.yaml"
    registry.write_text(
        "controls:\n"
        "  - id: X-1\n"
        "    framework: eu-ai-act\n"
        "    clause: some clause\n"
        "    obligation: o\n"
        "    control: k\n"
        "    evidence_module: atlas_conductor/does_not_exist.py\n"
        "    evidence_test: tests/conductor/test_governance_audit.py::test_intact_trail_verifies\n",
        encoding="utf-8",
    )
    dossier = tmp_path / "COMPLIANCE.md"
    dossier.write_text("X-1 some clause\n", encoding="utf-8")
    result = check_compliance(registry, dossier, _REPO_ROOT)
    assert not result.ok
    assert any("does_not_exist" in p for p in result.problems)


def test_a_citation_to_a_missing_test_node_fails(tmp_path: Path) -> None:
    registry = tmp_path / "controls.yaml"
    registry.write_text(
        "controls:\n"
        "  - id: X-1\n"
        "    framework: eu-ai-act\n"
        "    clause: some clause\n"
        "    obligation: o\n"
        "    control: k\n"
        "    evidence_module: atlas_conductor/governance/audit.py\n"
        "    evidence_test: tests/conductor/test_governance_audit.py::test_not_a_real_test\n",
        encoding="utf-8",
    )
    dossier = tmp_path / "COMPLIANCE.md"
    dossier.write_text("X-1 some clause\n", encoding="utf-8")
    result = check_compliance(registry, dossier, _REPO_ROOT)
    assert not result.ok
    assert any("test_not_a_real_test" in p for p in result.problems)


def test_a_placeholder_in_the_dossier_fails(tmp_path: Path) -> None:
    dossier = tmp_path / "COMPLIANCE.md"
    # A valid register row, but the dossier carries a stub.
    rows_text = default_registry_path().read_text(encoding="utf-8")
    (tmp_path / "controls.yaml").write_text(rows_text, encoding="utf-8")
    dossier.write_text(
        "EU-AIA-01 Annex IV §1 — general description & intended purpose (to confirm at review)\n",
        encoding="utf-8",
    )
    result = check_compliance(tmp_path / "controls.yaml", dossier, _REPO_ROOT)
    assert not result.ok
    assert any("placeholder" in p for p in result.problems)


def test_a_register_row_absent_from_the_dossier_fails(tmp_path: Path) -> None:
    registry = tmp_path / "controls.yaml"
    registry.write_text(
        "controls:\n"
        "  - id: X-1\n"
        "    framework: eu-ai-act\n"
        "    clause: a clause that is present\n"
        "    obligation: o\n"
        "    control: k\n"
        "    evidence_module: atlas_conductor/governance/audit.py\n"
        "    evidence_test: tests/conductor/test_governance_audit.py::test_intact_trail_verifies\n"
        "  - id: X-2\n"
        "    framework: iso-42001\n"
        "    clause: a clause that is absent\n"
        "    obligation: o\n"
        "    control: k\n"
        "    evidence_module: atlas_conductor/governance/audit.py\n"
        "    evidence_test: tests/conductor/test_governance_audit.py::test_intact_trail_verifies\n",
        encoding="utf-8",
    )
    dossier = tmp_path / "COMPLIANCE.md"
    # Only X-1 appears; X-2 is dropped.
    dossier.write_text("X-1 a clause that is present\n", encoding="utf-8")
    result = check_compliance(registry, dossier, _REPO_ROOT)
    assert not result.ok
    assert any("X-2" in p for p in result.problems)
