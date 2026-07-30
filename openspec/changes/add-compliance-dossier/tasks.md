## 1. Control register + compliance package (D-CMP-1)

- [x] 1.1 Add `atlas_conductor/compliance/__init__.py` and `compliance/registry.py` defining the frozen
  `ControlRow(id, framework, clause, obligation, control, evidence_module, evidence_test)` dataclass and
  a `load_registry(path) -> list[ControlRow]` that parses `compliance/controls.yaml` (JSON fallback per
  D-CMP-1). Add a unit test that the shipped register parses and every row has all fields populated.
- [x] 1.2 Author `compliance/controls.yaml` — the obligation→control→evidence rows for the EU AI Act
  Annex IV elements and ISO/IEC 42001 clauses the system addresses, each citing an existing module and
  test node (PHI gate, HITL gate, audit chain, egress guard, determinism, card drift-check).

## 2. The dossier document (compliance-dossier)

- [x] 2.1 Author `COMPLIANCE.md` at the repo root: the non-SaMD risk-tier determination up front, the
  honest non-certification scope statement (restating Model Card §6, D-CMP-6), and the obligation→control
  →evidence tables rendered from the register rows, grouped by framework.

## 3. CI drift + traceability check (D-CMP-2)

- [x] 3.1 Add `compliance/check.py` with `check_compliance(registry_path, dossier_path, test_root)`:
  resolve every `evidence_module` path, assert every `evidence_test` node exists/collectable in the test
  tree, assert no `(to confirm)`-style placeholder in `COMPLIANCE.md`, and assert every register row
  appears in the dossier.
- [x] 3.2 Add `tests/conductor/test_compliance_dossier.py` invoking `check_compliance` over the shipped
  register + dossier (passes), plus negative cases: a citation to a missing module fails, a placeholder
  in a temp dossier fails, and a register row absent from a temp dossier fails.

## 4. Run-scoped evidence bundle (D-CMP-3, D-CMP-4)

- [ ] 4.1 Add `compliance/evidence.py`: the frozen `EvidenceBundle` and
  `build_evidence(telemetry_dir) -> EvidenceBundle` — reads runs via `TelemetryReader`/`build_run_views`,
  loads audit entries and records `verify_audit_chain`'s verdict per run, extracts HITL
  holds/approvals/waivers and gate rejections from the audit trail, and attaches the register pass/fail
  summary.
- [ ] 4.2 Add JSON rendering (canonical, `sort_keys`) and optional self-contained HTML with no `<img>`
  and no `<script>` (mirroring `gui/export.py`).
- [ ] 4.3 Add tests: the bundle's per-slide verdicts and cohort counts equal `export-report`'s for the
  same run (shared-read-path invariant); the bundle reports the chain intact for an untampered trail and
  **broken** when an entry is altered (D-CMP-4); the rendered bundle contains no pixel/array/raw
  identifier (PHI-free).

## 5. CLI wiring (D-CMP-5)

- [ ] 5.1 Add an `export-dossier <telemetry-dir> [--format json|html]` Click subcommand to `cli.py`
  (read-only, mirroring `export-report`) that prints `build_evidence(...)` in the chosen format. Add a
  CLI test asserting JSON and HTML render for a recorded run.

## 6. Model Card + docs (D-CMP-6)

- [ ] 6.1 Update `MODEL_CARD.md` §10: flip the EU AI Act / ISO 42001 dossier line from "still planned"
  to "delivered", pointing at `COMPLIANCE.md`; confirm the card's drift-check still passes.
- [ ] 6.2 Add a short `export-dossier` usage note to the docs/README (alongside `export-report`),
  covering the evidence bundle and the `COMPLIANCE.md`/control-register pairing.

## 7. Validation

- [ ] 7.1 Run `openspec validate add-compliance-dossier --strict`, the full test suite, and ruff;
  confirm the phase adds no new runtime dependency and both the compliance check and the existing
  model-card check are green in CI.
