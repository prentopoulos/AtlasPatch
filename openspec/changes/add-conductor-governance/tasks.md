## 1. PHI-safe telemetry: pseudonymization + Safe-Harbor gate (D19, D20)

- [x] 1.1 Add `atlas_conductor/governance/phi.py` with a pure `pseudonymize_stem(stem, salt) -> str` (keyed HMAC-SHA256, `slide_<hex>`) and a `safe_harbor_findings(text) -> list[str]` matcher covering the Safe-Harbor identifier shapes (MRN/accession run, SSN, phone, email, IP/URL-with-id, dates finer than a year)
- [x] 1.2 Add `PhiSafeSink(TelemetrySink)` in `atlas_conductor/governance/gate.py` that wraps any inner sink: pseudonymize `slide_stem`, scan the remaining string fields, delegate on pass or fail-closed (drop + emit an audit rejection) on an unneutralizable Safe-Harbor match; derive the per-run salt from `job_id`
- [x] 1.3 Wrap the configured sink in `run.py` (`run_job` / `plan_job`) with `PhiSafeSink` so every component writes through the gate transparently
- [x] 1.4 Unit tests: an MRN-shaped stem is pseudonymized (not rejected); an MRN in a detail field is rejected; the same stem yields one pseudonym within a run and different pseudonyms across `job_id`s; a benign record passes through with only its stem changed

## 2. Egress containment proof (D23)

- [x] 2.1 Add a type-level test asserting every telemetry and audit record dataclass exposes only scalar/enum/str/int/path fields (no array/image-capable field)
- [x] 2.2 Add a network-guard test that runs a fake-adapter job with non-local socket connections stubbed to fail and asserts the core path opens no unexpected connection

## 3. HITL gate on irreversible/expensive actions (D21)

- [x] 3.1 Add `atlas_conductor/governance/hitl.py` with a pure `requires_confirmation(action) -> bool` (true for `FORCE_REPROCESS`, `BLOCK_JOB`, `QUARANTINE_ITEM`) and a `Confirmer` protocol with an attended default (hold when non-interactive) and an auto-approve used under `unattended`
- [x] 3.2 Consult the gate in `scheduler.py` immediately before `apply_recovery` for a proposed action: hold (record awaiting-confirmation, do not apply) when confirmation is required and not granted; apply otherwise; record the unattended waiver when `config.unattended`
- [x] 3.3 Unit tests: `force_reprocess` held in an attended run; bounded `retry_with_mutation` proceeds unprompted; unattended run auto-approves and logs the waiver; held slide state is recorded, not lost; policy classification matches the taxonomy exactly

## 4. Tamper-evident audit trail (D22)

- [x] 4.1 Add `atlas_conductor/governance/audit.py`: a hash-chained JSONL writer (`prev_hash`, `entry_hash = SHA256(prev_hash + canonical(payload))`) whose payloads pass through the PHI pseudonymizer, plus `verify_audit_chain(path)` returning intact / first-broken-link
- [x] 4.2 Append audit entries for consequential actions — each dispatch, each recovery decision, each HITL hold/approve/waive, each PHI-gate rejection — from the scheduler and the gate
- [x] 4.3 Unit tests: an intact trail verifies; an edited entry is detected at the right link; a deleted middle entry is detected; audit entries carry pseudonymized stems and no Safe-Harbor identifier

## 5. System/Model Card finalized and drift-checked (D24)

- [x] 5.1 Move `MODEL_CARD.md` into the repo (root), resolve every `(to confirm)` placeholder against the shipped code, and make the HITL and PHI sections name the implemented modules and match the gate's actual behavior
- [x] 5.2 Add a CI/test check asserting the card contains no `(to confirm)`-style placeholder and that each described safeguard names an implemented module

## 6. CI wiring and docs

- [ ] 6.1 Ensure the new tests (Safe-Harbor rejection, egress containment, HITL hold/waiver, audit tamper detection, Model Card no-placeholder) run in the `app` CI job with the fake adapter (no GPU)
- [ ] 6.2 Note the governance layer in the README/CHANGELOG where the phase-1 conductor is described, keeping the additive, upstream-untouched framing
- [ ] 6.3 Run `openspec validate add-conductor-governance --strict`, `ruff`, `mypy`, and the test suite; confirm all green before archiving
