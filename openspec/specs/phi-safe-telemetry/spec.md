# phi-safe-telemetry Specification

## Purpose
TBD - created by archiving change add-conductor-governance. Update Purpose after archive.
## Requirements
### Requirement: Slide stems are pseudonymized before persistence

The telemetry write path SHALL pseudonymize every slide-identifier field (the `slide_stem` of any record family) to a non-identifying token before the record is persisted or transmitted, so that the raw stem — which may itself be an MRN, accession number, or other identifier — never lands in any telemetry or audit store. The pseudonym SHALL be a deterministic function of the stem and a per-run salt, stable within a run so that a slide's records remain correlatable, and not reversible without the salt.

#### Scenario: A stem that is itself an identifier is neutralized, not stored raw

- **WHEN** a record whose `slide_stem` is an MRN-shaped or accession-shaped string is written
- **THEN** the persisted record carries a pseudonymized token in place of the raw stem, and the raw stem appears nowhere in the telemetry or audit store

#### Scenario: One slide's records stay correlatable within a run

- **WHEN** several records for the same slide are written during one run
- **THEN** they all carry the same pseudonym, so the slide's decision trace can still be reconstructed

#### Scenario: The same slide gets an unlinkable pseudonym across runs

- **WHEN** the same slide stem is written in two different runs (different `job_id`)
- **THEN** the two pseudonyms differ, so the raw identity cannot be recovered by cross-run comparison

### Requirement: HIPAA Safe-Harbor identifiers are rejected at write time

The telemetry write path SHALL reject any record whose fields contain a HIPAA Safe-Harbor identifier pattern that pseudonymization does not neutralize — for example an MRN/accession run, a Social Security number, a phone number, an email address, an IP address or URL bearing an identifier, or a date more specific than a year — appearing in a free-text field (such as a detail or reason tail). Rejection SHALL fail closed: the offending record is not persisted, the run continues, and the rejection is recorded in the audit trail.

#### Scenario: A leaked identifier in a detail field is rejected

- **WHEN** a record is written whose free-text detail field contains a Social-Security-number-shaped or MRN-shaped string
- **THEN** the record is not persisted and the rejection is recorded in the audit trail

#### Scenario: A PHI-laden stem injected via the fake adapter is caught in CI

- **WHEN** the fake adapter injects a slide whose stem carries a Safe-Harbor identifier and a run is executed
- **THEN** no raw identifier reaches the telemetry store — the stem is pseudonymized and any unneutralizable leak is rejected — provable by inspecting the store after the run

#### Scenario: A benign record passes through unchanged except for its stem

- **WHEN** a record with no Safe-Harbor identifier in any free-text field is written
- **THEN** it is persisted with only its `slide_stem` pseudonymized and all other operational fields intact

### Requirement: No PHI or pixel data can egress the layer

The orchestration layer SHALL guarantee that no whole-slide pixel data, tissue mask, or embedding matrix can leave the layer through telemetry or audit, enforced by type: no telemetry or audit record field is capable of holding an image or array. The layer's core run path (under the fake adapter) SHALL open no network connection to an unexpected external host, so that a run's only outbound surfaces are the AtlasPatch CLI invocation and on-disk HDF5.

#### Scenario: No record type can carry an array

- **WHEN** the telemetry and audit record types are inspected
- **THEN** every field accepts only a scalar, enum, timestamp, identifier, or path — none accepts an image, mask, or array

#### Scenario: A core run contacts no unexpected host

- **WHEN** a run is executed on the core path with the fake adapter and connections to non-local hosts are made to fail
- **THEN** the run completes without attempting any such connection
