## Context

Phases 1–5 built the operational core (planner / worker / validator / recovery over the
AtlasPatch CLI + HDF5), a PHI-free write-gated telemetry sink, a read-only GUI, an opt-in
A2A transport + BigQuery backend, and a content-addressed data-lineage layer. Recovery
classification is today a pure function, `recovery.classify(outcome, verdict) ->
(Classification, signature)`: hand-written stderr regexes (`_OOM_RE`, `_PRECONDITION_RE`)
plus a fixed set of structural verdict reasons, with everything unrecognized funnelled to
`unknown → block_item` (the safety invariant that misclassification never causes an unbounded
retry loop, failure-recovery spec).

Phase 1 built the labeled dataset this phase learns from **on purpose**. The
`slide_stage_outcomes` telemetry family carries `(signature, classification, action,
resolved)` for every recovery attempt, and the fake adapter's injections stamp an
`injected_label` ground-truth field into the `Outcome` (design D14; `contracts.Outcome.
injected_label`), "so CI can measure classifier accuracy vs truth." Nothing consumes that
label yet — this phase does.

The hard constraints from PROJECT.md carry in unchanged: `atlas_patch/` untouched;
metadata-only and PHI-free; operational-not-clinical (out of SaMD scope); heavy deps behind
`atlas-patch[orchestrator]` so `pip install atlas-patch` and the default CI path stay
credential-free and green. The one classification seam (`classify`) consumes only the
declarative `Outcome`/`Verdict` contracts, so swapping the implementation is a clean
substitution — exactly what PROJECT.md's phase-6 note means by "the declarative task contract
keeps this seam clean."

## Goals / Non-Goals

**Goals:**
- A `FailureClassifier` seam with `RuleClassifier` (default, stdlib — today's rules verbatim)
  and `LearnedClassifier` (opt-in), selected the way real/fake, jsonl/bigquery, and
  manifest/dvc already are, producing a `(Classification, signature, confidence)` result that
  `recovery.propose` consumes unchanged.
- A learned classifier trained from the `slide_stage_outcomes` recovery dataset against
  `injected_label`, deterministic (fixed seed, serialized weights), scored in CI against the
  fake adapter's ground truth with no dependency beyond core `numpy`.
- A **provable safety floor**: the learned classifier is never less safe than the rules. It
  abstains to the rule result on low confidence and may never upgrade a rule-blocked
  (`precondition-block`/`unknown`) failure into a retryable class.
- `train-classifier` and `eval-classifier` CLI subcommands over the read-only PHI-free
  telemetry path; a `run --classifier {rule,learned}` flag and `classifier:` config block,
  both defaulting to the rule path so a default run is byte-for-byte unchanged.
- The Model Card extended with the learned component's description for the phase-7 dossier.

**Non-Goals:**
- Replacing, weakening, or bypassing any safety invariant. The taxonomy, the action ladder,
  the attempt budget, the HITL gate, and "unknown → block" are unchanged; only *how a failure
  is mapped to a Classification* becomes learnable.
- A heavyweight ML stack. No scikit-learn, no torch, no GPU, no feature store. The model is a
  compact multinomial logistic regression in numpy; a richer sklearn-backed learner is
  explicitly deferred (see Open Questions), not shipped here.
- Online / continual learning, auto-retraining at run end, or a model registry. Training is an
  explicit, offline, human-invoked command producing a committable JSON artifact.
- Learning from, or featurizing, any clinical or pixel content. Features are drawn only from
  operational tool output and structural verdicts.
- Touching `atlas_patch/`, changing the five telemetry families' shapes, or adding a core
  dependency.

## Decisions

### D-LRC-1 — A `FailureClassifier` seam, mirroring the established backend pattern

Introduce `atlas_conductor/classifier/` with a `FailureClassifier` protocol:
`classify(outcome: Outcome | None, verdict: Verdict) -> ClassificationResult`, where
`ClassificationResult` is a frozen dataclass `(classification, signature, confidence)`.
`recovery.classify`'s body moves verbatim into `RuleClassifier.classify` (confidence fixed at
`1.0` — deterministic rules); the module-level `classify` function is retained as a thin
wrapper delegating to a shared `RuleClassifier` instance, so nothing outside the seam changes
behavior. `scheduler.py` holds a `FailureClassifier` (default `RuleClassifier`) and calls it
where it calls `classify(...)` today; `recovery.propose` is untouched and still consumes
`(classification, signature)` — `confidence` is used only by the seam's abstention logic, not
by the action ladder.

*Alternative considered:* have `LearnedClassifier` subclass/monkeypatch `recovery`. Rejected —
the protocol seam matches every other pluggable backend in the repo and keeps `recovery.py` a
pure proposer.

### D-LRC-2 — Operational-only, PHI-free, bounded feature vector

Features are extracted by a single pure function `features(outcome, verdict) -> np.ndarray`
over a **fixed, versioned vocabulary** of operational signals:
- Bernoulli presence flags for each token in a fixed operational stderr vocabulary
  (`cuda`, `out of memory`, `hf_token`, `gated`, `401`, `unauthorized`, `no module named`,
  `traceback`, `killed`, `timeout`, … — the same class of signal the regexes already key on),
  matched case-insensitively against `stderr_tail`.
- One-hot of the `verdict.reason` `ReasonCode` enum.
- Sign of `exit_code` (`0` / nonzero / absent).
- Attempt bucket (from `outcome`-carried context when present).

No free text, no slide stem, no path, no numeric image/embedding value ever enters the vector
— so the model is metadata-only and PHI-free *by construction*, and the serialized artifact
holds only learned coefficients indexed by this fixed vocabulary (no stderr strings survive
training). The vocabulary carries a `feature_version`; a model trained under one version
refuses to load against another, so a vocabulary change can never silently misalign weights.

*Alternative considered:* TF-IDF / hashing over raw stderr. Rejected — unbounded vocabulary
risks embedding path fragments or identifiers into the model and breaks the PHI-free-by-type
guarantee.

### D-LRC-3 — A compact, deterministic numpy model

`LearnedClassifier` wraps a multinomial logistic-regression `LinearModel` (weight matrix +
bias over the fixed feature dimension and the six `Classification` classes), trained by
deterministic mini-batch gradient descent with a fixed seed and fixed hyperparameters.
Serialization is JSON: `{feature_version, classes, weights, bias, config}`. Inference is a
pure numpy `softmax(x·W + b)`; `argmax` is the class, `max(softmax)` is the confidence.
Determinism (fixed seed + fixed data order) means the artifact is reproducible and inference
is a fixed function — the deterministic-core invariant holds, and there is no runtime clinical
reasoning.

*Alternatives considered:* multinomial naive Bayes (simpler but calibrates confidence poorly
for abstention); a decision tree (readable but brittle on the small vocabulary). Logistic
regression gives well-behaved softmax confidences, which the abstention floor (D-LRC-4)
depends on.

### D-LRC-4 — Safety-preserving abstention: the learned model is never less safe than the rules

`LearnedClassifier` composes with a `RuleClassifier` fallback and enforces two gates before
returning a learned class:
1. **Confidence gate:** if `max(softmax) < threshold` (config, default e.g. `0.6`), abstain
   and return the rule result (with the learned signature preserved for telemetry, marked
   abstained).
2. **Monotone-safety gate:** map each `Classification` to a *permissiveness rank* (block-class
   < quarantine-class < retry-class). If the rule classifier assigns a **blocking** class
   (`precondition-block`, `input-data`, or `unknown`) for the same input, the learned class
   may not exceed the rule class's permissiveness — i.e. the model may *tighten* a rule
   verdict but never *loosen* a rule-blocked failure into a retry. On violation it abstains to
   the rule result.

Together these make `LearnedClassifier` provably ≥ as safe as `RuleClassifier`: the
"unknown/precondition → block, never blind-retry" invariant (failure-recovery spec) is
preserved for *any* trained weights, including a pathologically bad model. `eval-classifier`
reports the **safety metric** — the fraction of should-block dataset rows the composed
classifier would retry — which is 0 by construction and asserted in CI as a regression guard.

*Alternative considered:* trust the model outright and rely on the attempt budget to bound
retries. Rejected — even bounded, blind-retrying a precondition failure (missing token) wastes
the whole budget and violates the spec's intent; the floor is cheap and categorical.

### D-LRC-5 — Training/eval over the read-only, PHI-free telemetry path

`train-classifier <telemetry-dir>` reads the `slide_stage_outcomes` family via the existing
`TelemetrySink.read_slide_stage_outcomes()` (the same read-only path the GUI, `export-report`,
and `lineage` use — it touches no run output), reconstructs a feature vector + label per row,
trains, and writes the JSON model. Label source precedence: `injected_label` when present
(fake-adapter ground truth), else the recorded `classification` (real-run self-labels). Rows
with neither are skipped. `eval-classifier` loads a model, scores a held-out split (or a
second telemetry dir), and prints accuracy, per-class precision/recall, and the D-LRC-4 safety
metric. Both are additive CLI verbs; neither alters a run.

*Alternative considered:* fold training into `run` at cohort end. Rejected — conflates a
read-only training step with a stateful run, and a run rarely has enough failures to train on;
explicit offline training over accumulated telemetry is the honest workflow.

### D-LRC-6 — Selection wiring: default is the rules, unchanged

`run` gains `--classifier {rule,learned}` (default `rule`) and an optional `classifier:`
config block (`{backend: rule|learned, model_path: ..., confidence_threshold: ...}`). A
`make_classifier(config)` factory in `run.py` mirrors `make_adapter` / `make_telemetry_sink` /
`make_lineage_backend`: `rule` returns `RuleClassifier()`; `learned` loads the model artifact
and returns a `LearnedClassifier(model, fallback=RuleClassifier(), threshold=...)`. A missing
or unloadable model (or a `feature_version` mismatch) logs and falls back to `rule` rather than
failing the run. The default `run` constructs `RuleClassifier` and is byte-for-byte identical
to current `main`.

## Risks / Trade-offs

- **A learned model overfits the fake adapter's synthetic injections and generalizes poorly to
  real stderr.** → The rules remain the default and the abstention floor means an
  underconfident learned model degrades *to the rules*, not below them. The learned path is
  opt-in; nobody is forced onto it. `eval-classifier` on a real-run telemetry dir surfaces the
  gap before anyone enables it.
- **Concept drift as AtlasPatch/CUDA evolve new error strings.** → The fixed vocabulary is
  operational and coarse (token presence, not exact strings); genuinely novel signatures score
  low-confidence and abstain to `unknown → block`, which is the safe default. Retraining is a
  one-command refresh over newer telemetry.
- **A vocabulary edit silently invalidating an old model.** → `feature_version` is stamped into
  the artifact and checked at load; a mismatch falls back to rules rather than feeding
  misaligned features.
- **PHI leaking into a model via stderr.** → Features are token-presence flags over a fixed
  vocabulary; raw stderr never enters the vector or the artifact. A unit test asserts a crafted
  stderr containing a fake identifier produces a feature vector and a serialized model that
  contain no substring of it.
- **Perception that a "learned classifier" makes clinical decisions (SaMD).** → Documented in
  the Model Card: features are operational tool output + structural verdicts only; the model
  never sees slide content and classifies *operational* failure modes. Out of clinical scope,
  same as the rest of the layer.

## Migration Plan

Purely additive. Ship the seam with `RuleClassifier` wired as the default so `main` behavior
is unchanged; land `LearnedClassifier`, the feature/model modules, and the CLI verbs behind
opt-in flags. No data migration, no config migration — existing job configs (no `classifier:`
block) run exactly as before. Rollback is dropping `--classifier learned` / the config block;
the artifact and subcommands are inert when unused.

## Open Questions

- **A richer sklearn-backed learner behind the `orchestrator` extra?** The seam and JSON model
  format are designed to admit a second `LearnedClassifier` training backend (guarded import,
  faked in CI, same artifact shape) exactly as `DvcLineage` sits beside `ManifestLineage`.
  Deferred to keep this phase reviewable; the numpy learner is sufficient to prove the seam and
  score against ground truth in CI.
- **Confidence threshold default and per-class thresholds.** Start with a single global default
  (~0.6) validated by `eval-classifier`; per-class thresholds can follow if evaluation shows a
  class systematically over/under-confident.
