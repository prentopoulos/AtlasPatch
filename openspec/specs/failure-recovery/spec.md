# failure-recovery Specification

## Purpose
TBD - created by archiving change add-atlas-conductor. Update Purpose after archive.
## Requirements
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

### Requirement: Recovery actions drawn only from CLI tuning knobs
The recovery agent SHALL choose actions only from a bounded set expressible through AtlasPatch's documented flags: `retry_as_is`, `retry_with_mutation` (over `--feature-batch-size`, `--seg-batch-size`, `--max-open-slides`, `--patch-workers`, `--feature-precision`), `force_reprocess` (`--force`), `quarantine_item`, `block_item`, `block_job`, and `mark_dependents_blocked`. Mutation ladders SHALL be monotone (tuning values only decrease) and bounded by a per-item attempt budget carried in the plan.

#### Scenario: OOM retried with a smaller batch
- **WHEN** a `resource-transient` OOM occurs and the attempt budget is not exhausted
- **THEN** the recovery agent proposes `retry_with_mutation` reducing `--feature-batch-size` to the next lower ladder value

#### Scenario: Attempt budget exhausted
- **WHEN** a `resource-transient` failure recurs after the attempt budget is exhausted
- **THEN** the recovery agent proposes `quarantine_item` rather than retrying again

#### Scenario: Structural-invalid rebuilt once
- **WHEN** a `structural-invalid` verdict is returned for the first time for a slide
- **THEN** the recovery agent proposes `force_reprocess`, and if the slide is still invalid it proposes `quarantine_item`

### Requirement: Unknown failures are never blindly retried
The recovery layer SHALL treat `unknown` classifications as non-retryable by default, proposing `block_item` and surfacing the raw stderr tail for human triage, so that misclassification never causes an unbounded retry loop. This SHALL hold for every classifier behind the seam: no classifier — rule-based or learned — may cause a failure that the rule-based classifier assigns to a blocking class (`precondition-block`, `input-data`, or `unknown`) to be retried, and a learned classifier SHALL abstain to the rule-based result rather than propose a less-safe action.

#### Scenario: Unclassified error blocks rather than loops
- **WHEN** an execution outcome does not match any known signature
- **THEN** the recovery agent proposes `block_item` and does not propose any retry

#### Scenario: Learned classifier cannot loosen a rule-blocked failure
- **WHEN** the learned classifier is selected and the rule-based classifier would block a failure as `precondition-block`, `input-data`, or `unknown`
- **THEN** the failure is still blocked and is not retried, regardless of the learned model's raw prediction

### Requirement: Downstream stages of a failed upstream are not scheduled
When a stage is blocked or quarantined, the recovery agent SHALL propose marking every stage that depends on it as `dependency-blocked`, and the planner SHALL NOT schedule a stage whose upstream dependency is not satisfied.

#### Scenario: Embed not scheduled after segment fails
- **WHEN** the `segment` stage for a slide is quarantined
- **THEN** that slide's `embed` stage is marked `dependency-blocked` and is never dispatched

### Requirement: Irreversible and expensive actions require human confirmation
When recovery proposes an action that overwrites existing outputs or terminates work — `force_reprocess`, `block_job`, or `quarantine_item` — the planner SHALL hold that action pending human confirmation before dispatch, unless the run is explicitly configured for unattended autonomy. Actions within the bounded, non-destructive set proceed without confirmation.

#### Scenario: Force-reprocess held for confirmation
- **WHEN** recovery proposes `force_reprocess` for a slide with an existing HDF5 and the run is not in unattended mode
- **THEN** the planner marks the action pending-confirmation and does not dispatch it until a human confirms

#### Scenario: Unattended mode proceeds without a prompt
- **WHEN** the run is explicitly configured for unattended autonomy
- **THEN** the proposed action is dispatched within its attempt budget and the decision is recorded in the audit trail

### Requirement: Recovery proposes, planner integrates
The recovery agent SHALL emit classifications and proposed plan-deltas and SHALL NOT mutate plan state directly; the planner SHALL be the single writer that integrates deltas into the plan.

#### Scenario: Proposed delta applied by planner
- **WHEN** the recovery agent proposes a `retry_with_mutation` for a slide
- **THEN** the planner integrates the delta and re-emits the plan, and no other component writes plan state
