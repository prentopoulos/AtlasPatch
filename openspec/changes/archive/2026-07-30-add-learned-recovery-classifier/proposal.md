## Why

The recovery agent classifies failures with a fixed set of hand-written stderr regexes and
verdict-reason rules (`recovery.classify`). New failure signatures the author never
anticipated fall through to `unknown` and block, and every taxonomy tweak means editing
code — even though phase 1 deliberately built the `slide_stage_outcomes` telemetry family as
a **labeled recovery dataset** (`signature`, `classification`, `action`, `resolved`, plus the
fake adapter's `injected_label` ground truth; design D14) precisely so a classifier could be
*learned* from real run history instead. This phase spends that seam: it adds a classifier
learned from the recovery dataset, without loosening any of the safety invariants the rules
guarantee today.

## What Changes

- Introduce a **`FailureClassifier` seam** — the single `classify(outcome, verdict) ->
  (Classification, signature, confidence)` interface the scheduler routes every failure
  through — with two implementations behind it, mirroring the established real/fake,
  jsonl/bigquery, manifest/dvc backend pattern:
  - **`RuleClassifier`** (default): the current `recovery.classify` rules, unchanged. It is
    the green-in-CI default *and* the safety floor the learned model can never fall below.
    A default `run` is byte-for-byte identical to today.
  - **`LearnedClassifier`** (opt-in): a compact model (multinomial logistic regression over a
    bounded, PHI-free **operational** feature set — presence of stderr tokens from a fixed
    vocabulary, the verdict reason-code one-hot, exit-code sign, attempt bucket) trained from
    the recovery dataset against `injected_label`. Trained with a fixed seed and serialized as
    a JSON weights file, so inference is deterministic and the whole train→score loop runs in
    CI with no cloud, no credentials, and no dependency beyond the already-core `numpy`.
- **Safety-preserving abstention**: when the learned model's top-class confidence is below a
  threshold, or when it would classify into a *more permissive* class than `RuleClassifier`
  does for a `precondition-block`/`unknown` signal, it **abstains and defers to the rules**.
  The learned classifier is therefore provably never less safe than the rules — it never turns
  a rule-blocked failure into a blind retry (preserving the "unknown → block" invariant).
- Add an `atlaspatch-conduct train-classifier <telemetry-dir>` subcommand (writes a model
  artifact) and `eval-classifier <telemetry-dir> --model <artifact>` (reports accuracy,
  per-class precision/recall, and a **safety metric**: the fraction of should-block failures
  the model would retry — required to be 0). Both use the same read-only, PHI-free path the
  GUI, `export-report`, and `lineage` use; neither touches a run's outputs.
- Wire selection through `run --classifier {rule,learned}` (default `rule`) and an optional
  `classifier:` job-config block naming a model artifact. `learned` with no/unloadable model
  falls back to `rule`.
- Extend the Model Card (phase 2) with a section describing the learned component — its
  operational-only feature set, training data, determinism, and the abstention floor — so the
  phase-7 compliance dossier inherits it.

## Capabilities

### New Capabilities
- `learned-recovery`: a `FailureClassifier` seam with a rule-based default and an opt-in
  learned classifier trained from the PHI-free recovery dataset; the deterministic,
  operational-only feature contract; the safety-preserving abstention floor; and the
  `train-classifier`/`eval-classifier` CLI subcommands and `classifier:` config block.

### Modified Capabilities
- `failure-recovery`: classification is now performed by a pluggable `FailureClassifier`
  rather than a hardcoded rule function; the requirement that unknown/precondition failures
  are never blindly retried is strengthened to bind *any* classifier, learned included.
- `model-card`: the card gains a learned-classifier section (training data, features,
  determinism, abstention floor).

## Impact

- **Code**: new `atlas_conductor/classifier/` (seam, rule + learned backends, feature
  extraction, model I/O, dataset reader); `recovery.classify` refactored into
  `RuleClassifier` behind the seam; `scheduler.py` routes classification through the selected
  classifier; `cli.py` gains two subcommands and a `--classifier` flag; `config.py`/`run.py`
  gain the `classifier:` block and a `make_classifier` factory. `MODEL_CARD.md` updated.
- **Dependencies**: none added — the learned model is pure `numpy` (already a core dep). No
  cloud, no credentials, no `orchestrator`-extra requirement for the default learned path.
- **Invariants preserved**: `atlas_patch/` untouched; features are operational-only (tool
  stderr tokens + structural verdict codes, never slide content), keeping the layer
  metadata-only, PHI-free, and out of clinical/SaMD scope; the model artifact stores only
  learned coefficients over the fixed vocabulary (no stderr text, no slide stems).
