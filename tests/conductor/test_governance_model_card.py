"""Drift check for the maintained System/Model Card (task 5.2).

Covers the ``model-card`` capability: the card ships in the repo with no unresolved
authoring placeholder, and each safeguard it describes names an implemented governance
module (design D24). A cheap grep keeps documentation honest the way tests keep code honest.
"""

from __future__ import annotations

import re
from pathlib import Path

import atlas_conductor
import atlas_conductor.governance as governance

_REPO_ROOT = Path(atlas_conductor.__file__).resolve().parent.parent
_CARD = _REPO_ROOT / "MODEL_CARD.md"
_GOVERNANCE_DIR = Path(governance.__file__).resolve().parent


def test_model_card_exists() -> None:
    assert _CARD.is_file(), "MODEL_CARD.md must be maintained in the repository root"


def test_model_card_has_no_unresolved_placeholder() -> None:
    text = _CARD.read_text(encoding="utf-8")
    # No "(to confirm)" / "_(to confirm at implementation)_" style stub may remain.
    assert not re.search(r"\(to confirm", text, re.IGNORECASE), "resolve all card placeholders"
    assert "TBD" not in text


def test_model_card_names_implemented_safeguard_modules() -> None:
    text = _CARD.read_text(encoding="utf-8")
    # Each safeguard the card describes must name a governance module that actually exists.
    for module in ("gate", "phi", "hitl", "audit"):
        assert (_GOVERNANCE_DIR / f"{module}.py").is_file(), f"missing governance module {module}"
        assert f"governance.{module}" in text, f"card does not name the {module} safeguard module"


def test_model_card_states_the_non_samd_boundary() -> None:
    text = _CARD.read_text(encoding="utf-8").lower()
    assert (
        "non-samd" in text or "not a diagnostic" in text or "software-as-a-medical-device" in text
    )
    # Honest compliance framing: technical safeguards, not a legal certification.
    assert "not" in text and "certification" in text
