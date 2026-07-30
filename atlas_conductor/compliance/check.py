"""The CI drift + traceability check that keeps the dossier honest (design D-CMP-2).

:func:`check_compliance` is what turns the dossier from *claim* into *evidence*: it parses
the control register, resolves every cited module path and test node against the repository,
forbids any unresolved authoring placeholder in ``COMPLIANCE.md``, and asserts every register
row is reflected in the rendered dossier. It is the Model Card drift-check (D24) generalized
from one document to the whole obligation map — so a control cannot be cited that the code
does not carry, and a shipped dossier cannot omit a registered control or leave a stub.

The check proves *existence and resolvability* of each citation (the named module file exists;
the named test function is defined in the named test file) — not semantic adequacy. Checking
the test *node exists* rather than re-running it keeps the check fast and decoupled from test
outcomes, which the ``app`` job already runs (design D-CMP-2). A human reviewer still vouches
that a cited test actually exercises its control; the register makes that spot-check cheap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from atlas_conductor.compliance.registry import ControlRow, load_registry

# Authoring stubs a released dossier must never carry (the D24 discipline, generalized).
_PLACEHOLDER_PATTERNS = (
    re.compile(r"\(to confirm", re.IGNORECASE),
    re.compile(r"\bTBD\b"),
    re.compile(r"\bTODO\b"),
    re.compile(r"\bFIXME\b"),
)


@dataclass(frozen=True)
class CheckResult:
    """The outcome of a compliance drift check: ``ok`` plus every problem found."""

    ok: bool
    problems: list[str] = field(default_factory=list)

    def raise_if_failed(self) -> None:
        if not self.ok:
            raise AssertionError(
                "compliance dossier check failed:\n  - " + "\n  - ".join(self.problems)
            )


def _test_node_exists(node: str, repo_root: Path) -> bool:
    """True if ``file.py::test_name`` resolves to a defined test function in the repo."""
    if "::" not in node:
        return False
    rel_path, _, test_name = node.partition("::")
    test_file = repo_root / rel_path
    if not test_file.is_file():
        return False
    source = test_file.read_text(encoding="utf-8")
    # Match the function definition, not an incidental mention of the name elsewhere.
    return re.search(rf"^\s*def {re.escape(test_name)}\b", source, re.MULTILINE) is not None


def _check_row(row: ControlRow, dossier_text: str, repo_root: Path) -> list[str]:
    problems: list[str] = []
    if not (repo_root / row.evidence_module).is_file():
        problems.append(f"{row.id}: evidence_module {row.evidence_module!r} does not exist")
    if not _test_node_exists(row.evidence_test, repo_root):
        problems.append(f"{row.id}: evidence_test {row.evidence_test!r} is not a defined test node")
    if row.id not in dossier_text:
        problems.append(f"{row.id}: control row does not appear in the dossier")
    if row.clause not in dossier_text:
        problems.append(f"{row.id}: clause {row.clause!r} does not appear in the dossier")
    return problems


def check_compliance(
    registry_path: str | Path | None,
    dossier_path: str | Path,
    repo_root: str | Path,
) -> CheckResult:
    """Resolve every register citation, forbid placeholders, enforce register⊆dossier.

    ``registry_path`` defaults (``None``) to the shipped register. ``dossier_path`` is
    ``COMPLIANCE.md``. ``repo_root`` is the root every ``evidence_module`` path and
    ``evidence_test`` file part is resolved against. Returns a :class:`CheckResult`; call
    :meth:`CheckResult.raise_if_failed` to make failure loud in a test.
    """
    root = Path(repo_root)
    dossier = Path(dossier_path)
    problems: list[str] = []

    rows = load_registry(registry_path)

    if not dossier.is_file():
        return CheckResult(False, [f"dossier not found: {dossier}"])
    dossier_text = dossier.read_text(encoding="utf-8")

    for pattern in _PLACEHOLDER_PATTERNS:
        match = pattern.search(dossier_text)
        if match:
            problems.append(f"dossier carries an unresolved placeholder: {match.group(0)!r}")

    for row in rows:
        problems.extend(_check_row(row, dossier_text, root))

    return CheckResult(not problems, problems)
