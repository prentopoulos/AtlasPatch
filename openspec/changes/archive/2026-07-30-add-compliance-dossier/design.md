## Context

Phases 1–6 built the operational core, the governance guardrails, the observability GUI, the A2A
distribution layer, data lineage, and the optional learned recovery classifier. Every one of those
phases produced a *verifiable technical safeguard with a CI proof* rather than an assertion — the PHI
write-gate (D12/D19–D20), the HITL gate (D13/D21), the tamper-evident hash-chained audit trail
(D22, `verify_audit_chain`), the egress containment proof (D23), and the drift-checked System/Model
Card (D24). The Model Card §10 already names this phase as the outstanding item: *"a full EU AI Act /
ISO 42001 compliance dossier building on this card and the audit trail."*

What is missing is the **map**. An assessor reading the EU AI Act's technical-documentation
requirements (Annex IV) or ISO/IEC 42001's management-system clauses has to reconstruct, from six
phases of specs and tests, which control answers which obligation. This phase writes that map down
once, backs it with a machine-checkable register so it cannot drift from the code, and adds a
**run-scoped evidence bundle** so a specific run can emit conformity evidence — the audit chain
actually verified, the governance decisions actually recorded — not just the standing prose.

The load-bearing facts that make this additive and dependency-free:
- The audit trail is already hash-chained and verifiable via `verify_audit_chain(entries)`
  (`atlas_conductor/governance/audit.py:159`); the evidence bundle *reads and verifies* it, adding no
  new integrity mechanism.
- `TelemetryReader` + `build_run_views` (`atlas_conductor/gui/model.py`, used by
  `atlas_conductor/gui/export.py`) is the single PHI-free read path the GUI and `export-report` share;
  the evidence bundle reuses it, so it cannot diverge from the report (report-export spec).
- The Model Card's drift-check (D24) already established the pattern of a governed doc verified in CI;
  the control register generalizes that pattern from one card to the whole obligation map.

Constraints (unchanged from PROJECT.md): `atlas_patch/` internals untouched; dossier and bundle read
only PHI-free telemetry and the audit trail; operational-not-clinical; no new runtime dependency. This
phase continues the prefixed decision-ID scheme used by recent phases (D-DIST, D-LIN, D-LRC) under the
**D-CMP** prefix.

## Goals / Non-Goals

**Goals:**
- Produce one maintained dossier (`COMPLIANCE.md`) that maps EU AI Act Annex IV elements and ISO/IEC
  42001 clauses to implemented controls, each row citing a module and a CI test, anchored by a
  defensible non-SaMD risk-tier determination.
- Make the map **un-rottable**: a structured control register (`compliance/controls.yaml`) is the
  single source of truth, a CI check proves every cited module/test exists and every row appears in the
  rendered dossier, and the dossier carries no unresolved placeholder — the same discipline as the
  Model Card check, generalized.
- Turn the standing dossier into **per-run evidence**: `export-dossier` verifies the run's audit chain
  and assembles its governance decisions + operational outcomes + register status into a PHI-free
  JSON/HTML bundle, sourced from the same read path as `export-report`.
- Keep everything additive, read-only over telemetry/audit, deterministic, and dependency-free.

**Non-Goals:**
- **Legal conformity / certification.** No CE marking, no ISO/IEC 42001 certificate, no attestation.
  The dossier documents *verifiable technical safeguards* and says so plainly; organizational,
  administrative, and physical measures (BAAs, audits, access policy, a deployed AIMS) are out of the
  system's control and out of scope — the same honesty line as the Model Card.
- **Re-classifying the system as high-risk / SaMD.** The determination is that it is *not*; this phase
  documents that boundary, it does not build the heavier obligations a high-risk system would trigger.
- **A conformity workflow or assessor portal.** The bundle is a static, exportable artifact (like
  `export-report`), not an interactive submission or e-signature system.
- **Cryptographic notarization of the dossier or bundle.** Tamper-*evidence* on the audit trail already
  exists (D22); the bundle surfaces it. Signing the dossier/bundle themselves is out of scope (as
  audit-log signing was in D22).
- **New telemetry or audit fields.** The bundle is a *reader*; it introduces no new record family and no
  write path. If the register wants a datum the records do not carry, that is a signal to reconsider,
  not to widen the schema here.

## Decisions

### D-CMP-1 — The control register is the single source of truth; the dossier renders from it
`compliance/controls.yaml` holds a list of control rows, each with: a stable `id`, the `framework`
(`eu-ai-act` | `iso-42001`) and `clause` it maps (e.g. `Annex IV §2(g) record-keeping`,
`ISO 42001 A.6.2.6 logging`), a one-line `obligation`, the `control` narrative, and `evidence` = the
`module` path plus the `test` node id (`tests/...::test_name`) that enforces it. `COMPLIANCE.md` is
rendered/authored to present exactly these rows (grouped by framework), plus the risk-tier
determination and scope-honesty prose. The register — not the prose — is what CI validates.
- **Why:** One structured source keeps the human-readable dossier and the machine-checkable evidence in
  lockstep. It is the D24 model-card discipline generalized: instead of grepping one doc for
  placeholders, we resolve every citation in a table. YAML (already in the dev toolchain via
  pre-commit/config) reads cleanly for a human reviewer; if a zero-dependency stance is preferred the
  same schema serializes to JSON with no code change.
- **Alternative considered:** author `COMPLIANCE.md` as free prose and grep it. Rejected — a prose-only
  dossier rots exactly like a prose-only card; a table of resolvable citations is testable, prose is not.

### D-CMP-2 — CI check resolves citations, forbids placeholders, and enforces register⊆dossier
A `check_compliance` routine (invoked by a test in the `app` job) (a) parses the register, (b) asserts
every `evidence.module` path exists and every `evidence.test` node is collectable/exists in the test
tree, (c) asserts the rendered `COMPLIANCE.md` contains no `(to confirm)`-style marker, and (d) asserts
every register `id`/clause appears in the dossier. Failure is loud and blocks merge.
- **Why:** This is what makes the dossier *evidence* rather than *claim*: a control cannot be cited that
  the code does not implement, and a shipped dossier cannot omit a registered control or leave a stub.
  Reusing the collect-the-test-node idea keeps the citation honest down to the specific proof.
- **Alternative considered:** check only that modules exist, not tests. Rejected — the test node is the
  actual proof; citing a module without its enforcing test is the weaker claim the register exists to
  prevent. Checking test *existence* (not re-running each in the checker) keeps the check fast and
  avoids coupling to test outcomes, which the `app` job already runs.

### D-CMP-3 — The evidence bundle is a reader over the shared telemetry/audit path (implements compliance-evidence)
`atlas_conductor/compliance/evidence.py` exposes `build_evidence(telemetry_dir) -> EvidenceBundle` that:
reads runs via `TelemetryReader`/`build_run_views` (the same structure `export-report` uses, so
per-slide verdicts and counts are identical by construction); loads the audit entries and calls
`verify_audit_chain` to record intact-vs-broken; extracts the HITL holds/approvals/waivers and gate
rejections from the audit trail; and attaches the static control-register pass/fail summary. It renders
to JSON (canonical) and optional scripts-and-images-free HTML, mirroring `export.py`.
- **Why:** Sourcing from the one shared read path is exactly the report-export invariant (the bundle and
  the report can't disagree), and it means the bundle inherits the PHI-free guarantee for free — it never
  touches a raw stem or a pixel because that path never exposes one.
- **Alternative considered:** a fresh reader that re-parses telemetry. Rejected — a second read path is a
  second thing to keep consistent and a second place PHI discipline could slip; reuse is the safer and
  smaller choice.

### D-CMP-4 — The bundle *verifies* the chain, never asserts it
The bundle always runs `verify_audit_chain` and reports its verdict; it never emits "intact" without
having verified. A run with a tampered audit trail is reported as **broken** (with the first broken
link, as `verify_audit_chain` already returns), so the bundle cannot launder a tampered run into
conformity evidence.
- **Why:** The whole value of a hash chain (D22) is that evidence is *checked*, not trusted. A bundle
  that printed a stored "intact" flag would defeat the tamper-evidence it is meant to present.
- **Alternative considered:** trust a status recorded at run end. Rejected — that status is inside the
  trail the check is meant to validate; verifying at export time is the only sound order.

### D-CMP-5 — `export-dossier` CLI mirrors `export-report`; PHI-free HTML has no `<img>`/scripts
A new `export-dossier <telemetry-dir> [--format json|html]` Click subcommand (read-only, like
`export-report` at `cli.py:121`) prints the bundle. HTML is self-contained with no `<img>` and no
`<script>` — the same rule `export.py` follows — so an exported bundle can be opened or attached without
carrying or fetching anything.
- **Why:** Operators already know `export-report`; a parallel `export-dossier` needs no new mental model,
  and the no-image/no-script HTML rule keeps the artifact safe to circulate.
- **Alternative considered:** fold the evidence into `export-report --compliance`. Rejected — the report
  is the operational sibling (verdicts for operators); the evidence bundle is a conformity artifact
  (chain verification + governance decisions + control status) for a different reader. Distinct commands
  keep each artifact's audience and content clear, and the `compliance-evidence` capability its own seam.

### D-CMP-6 — Model Card updated to point at the delivered dossier; scope-honesty text is shared
Model Card §10 flips the phase-7 line from "still planned" to "delivered → `COMPLIANCE.md`", and the
dossier's non-certification scope paragraph restates (does not contradict) the card's §6 honesty
framing. The card's *requirements* do not change — this is a content update the existing card
drift-check already covers.
- **Why:** The two governed docs must agree; the card is the system's front door and should point at its
  dossier. Keeping the model-card capability's requirements untouched keeps this phase additive.

## Risks / Trade-offs

- **The register can cite a test that exists but does not actually prove the control.** → The CI check
  proves *existence and resolvability* of the citation, not semantic adequacy — a human reviewer still
  vouches that the named test exercises the control. This is the same bound the Model Card check has
  (it proves no placeholder, not that the prose is true); the register makes the claim *auditable* and
  cheap to spot-check, which is the achievable improvement. Mitigation: the review checklist for this
  PR includes reading each cited test.
- **Framework mappings are interpretive.** EU AI Act Annex IV and ISO 42001 clauses do not map 1:1 onto
  an operational orchestrator. → The dossier is explicit that it maps *applicable* obligations under a
  documented non-SaMD determination, and states its scope honestly; it does not claim exhaustive
  coverage or conformity. The determination itself is the load-bearing argument and is stated up front
  so a reviewer can challenge it directly.
- **A YAML register adds a parse dependency if we want strict zero-deps.** → PyYAML is already present in
  the dev/test toolchain; if the core `app` job must stay YAML-free, the register serializes to JSON with
  no schema change (D-CMP-1). Decide at implementation which the `app` job already has.
- **The dossier could drift from the card.** → Both are governed docs with CI checks; §10 of the card and
  the dossier cross-reference each other, and the card drift-check already fails on stale placeholders.
  The shared scope-honesty wording is small and reviewed together in this one PR.
- **Register⊆dossier is enforced, dossier⊆register is not** — the dossier may add narrative the register
  doesn't. → Intended: the register is the *checked minimum*, the dossier may contextualize. The check
  guarantees no registered control is silently dropped from the dossier, which is the failure mode that
  matters.

## Open Questions

- **Register format: YAML vs JSON.** Leaning YAML for reviewer readability, contingent on the `app` job
  already having a YAML parser; falls back to JSON (zero-dep) otherwise. Resolve against the CI env at
  implementation (per the [[atlaspatch-ci-mypy-optional-deps]] note that CI deps are lean).
- **Dossier location: repo root vs `docs/`.** Defaulting to repo root to sit beside `MODEL_CARD.md`
  (matches D24's placement choice and maximizes visibility); revisit only if the top level is felt to be
  crowding.
- **Evidence-bundle scope: latest run vs all runs.** `export-report` renders all runs in a telemetry
  dir; the evidence bundle likely wants the same "all runs present, each with its own chain verdict"
  shape for consistency. Confirm during implementation that per-run chain verification composes cleanly
  when a directory holds multiple runs.
