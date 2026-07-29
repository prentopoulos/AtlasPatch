## Context

Phase 1 (`add-atlas-conductor`) shipped the deterministic operational core: planner / worker / validator / recovery over the AtlasPatch CLI, with a typed, append-only, metadata-only telemetry sink (`atlas_conductor/telemetry.py`). Its design doc already reserved the governance decisions this change implements — **D9** (metadata-only by type), **D12** (PHI-free by construction, extends D9), **D13** (HITL on irreversible/expensive actions, extends D7) — and its scope note (D17, "Run B") named this exact bundle: *HITL gate, PHI-free write gate, tamper-evident audit trail, egress assertion, Model Card, and the CI proofs.* The phase-1 `MODEL_CARD.md` is a DRAFT stub with `(to confirm at implementation)` placeholders.

The load-bearing fact is that phase 1 already made the record shapes correct (frozen dataclasses of scalars/enums/ids; no method accepts an array), so every guardrail here is a **filter or gate placed in front of already-correct components**, never a change to their contracts. The seams that make this additive:

- `TelemetrySink` (ABC) — every write goes through four `record_*` methods. A decorator that also implements `TelemetrySink` can pseudonymize and reject before delegating.
- The scheduler applies a `RecoveryProposal`'s action via `self._planner.apply_recovery(...)` (`scheduler.py:204`). A gate consulted immediately before that call can hold an irreversible action.
- `JobConfig.unattended` (`config.py:47`) already exists as the autonomy flag.
- Slide stems are the only free-text identifier that flows into records (`slide_stem` on three of the four families); everything else is enums, ints, timestamps, and paths.

Constraints (unchanged from PROJECT.md): `atlas_patch/` internals untouched; telemetry metadata-only and PHI-free; operational-not-clinical; heavy deps behind the extra. The gates add **no new runtime dependency** — pseudonymization is `hashlib`, Safe-Harbor matching is `re`, the audit chain is `hashlib` + JSONL, all stdlib.

## Goals / Non-Goals

**Goals:**
- Make the phase-1 safety assertions **enforced and CI-provable**, not documented: a PHI-laden stem is rejected/pseudonymized at write time; no unexpected host is contacted; irreversible actions pause for a human unless explicitly waived; the audit log detects tampering; the Model Card carries no unfilled placeholder.
- Keep every guardrail **additive** — a decorator/gate in front of a phase-1 component, so the union with phase 1 changes behavior only by *adding* rejections/holds, never by altering an accepted path.
- Preserve determinism (D11): pseudonymization and Safe-Harbor matching are pure functions of the record; the HITL decision is a pure function of `(action, unattended)`.

**Non-Goals:**
- Legal HIPAA/GDPR **certification**. These are verifiable *technical safeguards* (necessary conditions), explicitly not a compliance attestation — the Model Card says so.
- Cryptographic non-repudiation / signed audit logs with external notarization. Tamper-*evidence* (a hash chain that makes edits detectable) is in scope; tamper-*proofing* (append-only WORM storage, HSM signing) is not.
- A HITL **UI** or approval queue. The gate is a synchronous confirmation seam (callback/prompt) with an unattended bypass; the phase-3 GUI is read-only and does not yet drive confirmations (design D18).
- Deep PHI inspection of WSI *pixels* or HDF5 *contents* — those never enter telemetry by type (D9); the gate guards the identifiers that do (stems and free-text detail fields).
- Re-deriving Safe-Harbor as a clinical NLP de-identifier. The matcher targets the 18 Safe-Harbor identifier *shapes* in short operational strings, not narrative de-identification.

## Decisions

### D19 — PHI gate is a `TelemetrySink` decorator, not a sink rewrite (implements D12)
A `PhiSafeSink(TelemetrySink)` wraps any inner sink (`JsonlTelemetrySink`, `InMemoryTelemetrySink`, the phase-4 BigQuery sink). Each `record_*` method (a) pseudonymizes the `slide_stem` field, (b) scans every string field against the Safe-Harbor matcher, and (c) either delegates to the inner sink or rejects. The run façade (`run.py`) wraps the configured sink once, so every component writes through the gate without knowing it exists.
- **Why:** The `TelemetrySink` ABC is the single write chokepoint; a decorator makes the gate universal and backend-agnostic (the same gate protects the BigQuery backend in phase 4 for free) and leaves the phase-1 sinks untouched.
- **Alternative considered:** push pseudonymization into each record's construction site. Rejected — spreads the invariant across every caller and is un-auditable; the decorator is one enforced boundary.

### D20 — Pseudonymize by deterministic keyed hash; reject only true Safe-Harbor shapes
Stems are pseudonymized to `slide_<hex>` where `<hex>` is a truncated HMAC-SHA256 of the stem under a per-run salt derived from `job_id` (stable within a run, so the decision trace and GUI can still correlate a slide across records; not reversible without the salt). Rejection is reserved for records whose *other* string fields (detail tails, reason text) contain a Safe-Harbor identifier pattern the pseudonymizer cannot neutralize — MRN/accession runs, SSN, phone, email, explicit dates finer than a year, IP/URL with an identifier. A stem that is *itself* an MRN is neutralized by pseudonymization (the raw stem never persists); a detail field carrying a leaked MRN is rejected loudly.
- **Why:** Pseudonymization keeps telemetry *useful* (per-slide correlation survives) while guaranteeing the raw identifier never lands; rejection is the backstop for identifiers that appear where pseudonymization doesn't reach. Deterministic-per-run keying is what lets the D15 decision trace and D18 GUI still group a slide's events.
- **Alternative considered:** drop/blank all stems. Rejected — destroys the per-slide accounting that is the layer's whole point. Random per-record tokens: rejected — breaks correlation.
- **Alternative considered:** reject on *any* Safe-Harbor match including the stem. Rejected — a hospital's stems are frequently accession-shaped; rejecting them would make the tool unusable on real cohorts, whereas pseudonymization is the correct HIPAA-aligned treatment.

### D21 — HITL gate is a policy function + injectable confirmer (implements D13)
Two pieces: a pure policy `requires_confirmation(action) -> bool` (true for `FORCE_REPROCESS`, `BLOCK_JOB`, `QUARANTINE_ITEM`; false for the bounded/non-destructive rest), and a `Confirmer` protocol the scheduler consults when the policy says a hold is needed. `unattended=True` short-circuits to auto-approve **and records the waiver** in the audit trail. The default attended `Confirmer` in a non-interactive/CI context denies-by-holding (the action is not taken and the slide is recorded as awaiting confirmation), so CI is deterministic without a human.
- **Why:** Separating the *policy* (which actions are gated — pure, testable, matches the Model Card table exactly) from the *mechanism* (how a human answers — injectable) keeps the decision auditable and lets CI drive both branches (waived vs. held) with a fake confirmer. Reusing `unattended` avoids new config surface.
- **Alternative considered:** gate inside the recovery agent. Rejected — recovery is a pure classifier/proposer (D6); it must stay side-effect-free. The gate belongs at the apply site in the scheduler, the single writer path.

### D22 — Audit trail is a hash-chained JSONL sibling of telemetry, not a fifth telemetry family
Consequential actions — every dispatch, every recovery decision, every HITL hold/approve/waive, every PHI-gate rejection — are appended to `audit.jsonl` where each entry carries `prev_hash` and `entry_hash = SHA256(prev_hash + canonical(payload))`, forming a chain. A `verify_audit_chain()` walks the file and reports the first broken link. The audit payloads are themselves PHI-gated (they go through the same pseudonymizer), so the audit trail cannot become a PHI side channel.
- **Why:** A hash chain makes any post-hoc edit or deletion detectable with stdlib only — the "tamper-evident" bar — without a database or signing infra (a Non-Goal). Keeping it a *separate* file (not a new `TelemetrySink` family) means the integrity mechanism (chaining) doesn't complicate the append-only telemetry families the GUI and report already read, and its verification is independent.
- **Alternative considered:** add `audit_events` as a fifth telemetry family. Rejected — telemetry families are plain append rows optimized for reconstruction/readback; bolting a hash chain onto one family would couple integrity to the readback path and the phase-4 BigQuery schema. A dedicated chained log is cleaner and independently verifiable.
- **Alternative considered:** sign each entry (Ed25519). Deferred — key management is out of scope; chaining is sufficient for tamper-*evidence*.

### D23 — Egress containment is proven by type + a network guard test, not a runtime firewall
Two-layer proof: (1) *by type* — no telemetry/audit field can hold a pixel/array (already true from D9, re-asserted by a test that the record dataclasses expose only scalar/enum/str/int/path fields); (2) *by test* — a run under the fake adapter executes with socket creation to non-local hosts stubbed to fail, asserting the core path opens no unexpected connection. The real subprocess adapter (which *does* legitimately reach HuggingFace for encoder weights) is out of the core CI path (phase-1 D17), so the guard covers the orchestration layer's own egress, not AtlasPatch's model downloads.
- **Why:** A CI-enforceable assertion is worth more than a documented promise. Proving it at the type level (structural) plus a no-surprise-socket test (behavioral) matches how D9's metadata-only claim is proven and gives phase 4 a concrete bar its BigQuery backend must clear.
- **Alternative considered:** OS-level network namespace/firewall in CI. Rejected — platform-specific (Windows dev box, D-notes), heavy, and tests the sandbox rather than the code. Socket stubbing is portable and targets our code.

### D24 — Model Card is finalized in-repo and drift-checked, treated as a governed artifact
`MODEL_CARD.md` moves from the archived phase-1 change into the repo root (or `docs/`), placeholders resolved against the shipped code, and a CI check asserts no `(to confirm)` / `_(to confirm at implementation)_` markers remain and that each guardrail section names an implemented module. It stays honest about scope: verifiable technical safeguards, explicitly **not** a legal HIPAA certification, and the non-SaMD boundary stated as an invariant.
- **Why:** Phase 7's EU AI Act / ISO 42001 dossier builds directly on this card (PROJECT.md); a drifting or placeholder-laden card would undermine that. A cheap placeholder-grep in CI keeps documentation honest the same way tests keep code honest.
- **Alternative considered:** leave the card as prose only. Rejected — untested docs rot; the drift check is near-free.

## Risks / Trade-offs

- **Safe-Harbor matcher is heuristic (regex over identifier shapes).** → It is a backstop, not the primary control — pseudonymization is what actually protects stems (the common case). False negatives on exotic identifier formats are mitigated by (a) the by-type guarantee that no free-form clinical narrative ever enters a record, and (b) logging the *shape* that triggered a rejection for tuning. False positives (rejecting a benign string) surface loudly in the audit trail and fail closed (the record is dropped, the run continues), which is the safe direction.
- **Pseudonymization is reversible by anyone holding the per-run salt.** → By design: within-run correlation requires a stable mapping. The salt is derived from `job_id` and never persisted alongside the hashes in a way that ships off-box; this is pseudonymization (HIPAA-aligned), not anonymization, and the Model Card states so plainly.
- **Hash-chain tamper-evidence detects edits but does not prevent them.** → In scope is *evidence*, not *prevention* (Non-Goal); `verify_audit_chain()` is the detection surface, and the chain is cheap enough to verify on every GUI load or report render.
- **HITL default-hold could stall an unattended-by-accident batch.** → The behavior is intentional fail-safe: an irreversible action never runs without either a human yes or an explicit `unattended: true`. The held slide is recorded (not lost), so the operator sees exactly what awaits confirmation.
- **Gate ordering matters** (pseudonymize before Safe-Harbor scan, audit after gate). → Fixed, documented order in `PhiSafeSink`; unit-tested with a stem that is an MRN (must pseudonymize, not reject) vs. a detail field with an MRN (must reject).

## Migration Plan

Additive only; no data migration. Rollout: add the gate modules; wrap the sink in `run.py`; insert the HITL consult before `apply_recovery`; open the audit log alongside telemetry; move and finalize `MODEL_CARD.md`; wire the five CI proofs into the `app` job. Rollback = unwrap the sink and remove the consult (the phase-1 path is unchanged underneath), delete the new modules; telemetry and recovery behave exactly as in phase 1. AtlasPatch is unaffected — nothing in `atlas_patch/` changes.

## Open Questions

- **Salt lifetime beyond a run.** Per-run (`job_id`-derived) salt means the *same* slide gets *different* pseudonyms across two jobs, so cross-run history in the GUI (phase 3) can't correlate a slide. Is per-run correct, or should the salt be per-cohort/per-deployment (stable across runs, wider correlation, slightly larger reversal surface)? Leaning per-run for the MVP; revisit when the GUI adds cross-run history.
- **Audit-chain root/anchoring.** The chain's genesis `prev_hash` is a constant; should the root be anchored (e.g. logged to the telemetry `jobs` family) so a wholesale file replacement is also detectable, not just in-place edits? Cheap to add; deciding whether it belongs in this phase or the phase-7 dossier.
- **Model Card location** — repo root vs. `docs/`. Root maximizes visibility; `docs/` keeps the top level clean. Defaulting to repo root to match the phase-1 archive's placement and CHANGELOG conventions.
