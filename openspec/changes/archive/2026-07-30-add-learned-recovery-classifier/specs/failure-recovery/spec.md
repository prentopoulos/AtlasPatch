## MODIFIED Requirements

### Requirement: Failures classified from two sources into a bounded taxonomy
The recovery agent SHALL classify failures arising from two sources — execution failures surfaced by the worker (nonzero exit, stderr signature, crash) and structural failures surfaced by the validator on otherwise-successful invocations — into a bounded taxonomy: `resource-transient`, `precondition-block`, `input-data`, `structural-invalid`, `dependency-blocked`, and `unknown`. Classification SHALL be performed through a single pluggable classifier seam consuming only the declarative `Outcome` and `Verdict` contracts; the taxonomy SHALL be identical regardless of which classifier (rule-based or learned) is selected.

#### Scenario: OOM classified as resource-transient
- **WHEN** an execution outcome carries a CUDA-OOM stderr signature
- **THEN** the recovery agent classifies it `resource-transient`

#### Scenario: Missing gated-model token classified as precondition-block
- **WHEN** an execution outcome indicates a missing Hugging Face token or an unavailable gated/uninstalled encoder
- **THEN** the recovery agent classifies it `precondition-block`

#### Scenario: Validator row mismatch classified as structural-invalid
- **WHEN** the validator reports a feature/coord row mismatch or NaNs
- **THEN** the recovery agent classifies it `structural-invalid`

#### Scenario: Classifier choice does not change the taxonomy
- **WHEN** the learned classifier is selected instead of the rule-based default
- **THEN** every classification it returns is a member of the same bounded taxonomy, and the downstream action ladder consumes it unchanged

### Requirement: Unknown failures are never blindly retried
The recovery layer SHALL treat `unknown` classifications as non-retryable by default, proposing `block_item` and surfacing the raw stderr tail for human triage, so that misclassification never causes an unbounded retry loop. This SHALL hold for every classifier behind the seam: no classifier — rule-based or learned — may cause a failure that the rule-based classifier assigns to a blocking class (`precondition-block`, `input-data`, or `unknown`) to be retried, and a learned classifier SHALL abstain to the rule-based result rather than propose a less-safe action.

#### Scenario: Unclassified error blocks rather than loops
- **WHEN** an execution outcome does not match any known signature
- **THEN** the recovery agent proposes `block_item` and does not propose any retry

#### Scenario: Learned classifier cannot loosen a rule-blocked failure
- **WHEN** the learned classifier is selected and the rule-based classifier would block a failure as `precondition-block`, `input-data`, or `unknown`
- **THEN** the failure is still blocked and is not retried, regardless of the learned model's raw prediction
