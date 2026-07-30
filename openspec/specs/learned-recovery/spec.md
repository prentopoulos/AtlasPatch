# learned-recovery Specification

## Purpose
TBD - created by archiving change add-learned-recovery-classifier. Update Purpose after archive.
## Requirements
### Requirement: Classification is performed by a pluggable classifier behind one seam

The recovery layer SHALL route every failure classification through a single
`FailureClassifier` seam that consumes only the declarative `Outcome` and `Verdict` contracts
and returns a `(classification, signature, confidence)` result. The system SHALL provide a
rule-based classifier (the existing hand-written rules) as the default and an opt-in learned
classifier behind the same seam, selected the way other pluggable backends are. The default
selection SHALL be the rule-based classifier, so a run that does not opt in behaves exactly as
before.

#### Scenario: Default run uses the rule-based classifier

- **WHEN** a job runs without selecting a classifier
- **THEN** classification is performed by the rule-based classifier and the run's behavior is
  identical to the pre-existing rule-based recovery

#### Scenario: Learned classifier selected explicitly

- **WHEN** a run selects the learned classifier and a valid model artifact is available
- **THEN** classification is performed by the learned classifier behind the same seam, and
  `recovery.propose` consumes its `(classification, signature)` result unchanged

#### Scenario: Unloadable model falls back to the rules

- **WHEN** the learned classifier is selected but its model artifact is missing, unreadable, or
  its feature version does not match the running code
- **THEN** the system falls back to the rule-based classifier rather than failing the run

### Requirement: Learned classifier features are operational-only and PHI-free

The learned classifier SHALL derive its features only from operational signals — presence of
tokens from a fixed operational stderr vocabulary, the structural verdict reason code, the
exit-code sign, and the attempt count — and SHALL NOT featurize any slide pixels, embeddings,
raw free-text stderr, slide stems, or filesystem paths. The serialized model artifact SHALL
contain only learned coefficients indexed by a versioned feature vocabulary, and SHALL NOT
contain raw stderr text or any input identifier.

#### Scenario: No raw failure text survives into the model

- **WHEN** a model is trained from telemetry whose failures contain an arbitrary identifier
  string in their stderr
- **THEN** neither the extracted feature vector nor the serialized model artifact contains any
  substring of that identifier

#### Scenario: Feature version guards against silent misalignment

- **WHEN** a model artifact's feature version does not match the running code's feature
  vocabulary
- **THEN** the model is refused and the rule-based classifier is used instead

### Requirement: The learned classifier is never less safe than the rules

The learned classifier SHALL enforce a safety floor relative to the rule-based classifier: it
SHALL abstain and defer to the rule result when its top-class confidence is below a configured
threshold, and it SHALL NOT classify a failure the rule-based classifier assigns to a blocking
class (`precondition-block`, `input-data`, or `unknown`) into a more-permissive, retryable
class. As a result, enabling the learned classifier SHALL NOT cause any failure to be retried
that the rule-based classifier would have blocked.

#### Scenario: Low confidence abstains to the rules

- **WHEN** the learned classifier's top-class confidence is below the configured threshold for
  a failure
- **THEN** it returns the rule-based classifier's classification for that failure

#### Scenario: A rule-blocked failure is never upgraded to a retry

- **WHEN** the rule-based classifier would classify a failure as `precondition-block`,
  `input-data`, or `unknown`
- **THEN** the learned classifier does not return a retryable classification for that failure,
  regardless of the trained model's raw prediction

### Requirement: A classifier is trained and evaluated from the PHI-free recovery dataset offline

The system SHALL provide commands to train a learned-classifier model from a run's
`slide_stage_outcomes` telemetry (the labeled recovery dataset) and to evaluate a model,
reading telemetry through the same read-only, PHI-free path used by the GUI and lineage and
writing no run output. Training SHALL use the fake-adapter `injected_label` as ground truth
when present and the recorded classification otherwise, and SHALL be deterministic for a fixed
dataset and seed. Evaluation SHALL report classification accuracy and a safety metric equal to
the fraction of should-block failures the classifier would retry.

#### Scenario: Training reads telemetry read-only and emits a model artifact

- **WHEN** the train command is run against a telemetry directory
- **THEN** it reads only the telemetry, writes a model artifact, and leaves the run's outputs
  and telemetry unchanged

#### Scenario: Training is deterministic

- **WHEN** the train command is run twice over the same dataset with the same seed
- **THEN** it produces identical model artifacts

#### Scenario: Evaluation reports accuracy and the safety metric

- **WHEN** the eval command is run against a model and a labeled telemetry dataset
- **THEN** it reports classification accuracy and a safety metric, and the safety metric of the
  composed learned classifier is zero (no should-block failure would be retried)
