# report-export Specification

## Purpose
TBD - created by archiving change add-conductor-gui. Update Purpose after archive.
## Requirements
### Requirement: Machine-readable report sibling
The conductor SHALL be able to emit an HTML and/or JSON sibling of the terminal report,
carrying the same per-slide outcomes, reason codes, decision traces, and cohort counts the
terminal report presents. The sibling SHALL be sourced from the same telemetry/audit records
as the terminal report, not recomputed from a separate path.

#### Scenario: JSON sibling mirrors the terminal report
- **WHEN** the report is exported as JSON for a completed run
- **THEN** it contains each slide's terminal outcome and reason code and the cohort
  valid/skipped/quarantined/blocked counts, matching the terminal report

#### Scenario: Export carries no PHI and no pixels
- **WHEN** a report sibling is exported for a run that gated its telemetry
- **THEN** it contains only PHI-free operational metadata — pseudonymized stems, verdicts,
  reason codes, counts — and no slide pixel, mask, embedding, or raw identifier

### Requirement: Export shares the GUI's read surface
The report-export data SHALL be produced from the same telemetry read path the GUI uses, so
the exported sibling and the GUI panels cannot diverge in what they report for a run.

#### Scenario: Export and GUI agree on a run
- **WHEN** the same run is rendered in the GUI and exported as a report sibling
- **THEN** the per-slide verdicts and cohort counts are identical in both
