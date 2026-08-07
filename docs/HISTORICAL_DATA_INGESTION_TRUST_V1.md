# Historical Data Ingestion & Trust v1

## Purpose

Historical Data Ingestion & Trust v1 is the deterministic boundary between a source export and Neraium behavioral analysis. It turns BAS, BMS, SCADA, historian, controller, and other operational exports into an inspectable canonical dataset without treating a guess, repair, or anomaly as fact.

The governing rule is: **automate aggressively, guess conservatively, and record everything**.

## Scope

Version 1 covers delimited historical files and existing JSON telemetry exports accepted by the upload workflow. JSON is retained byte-for-byte and projected into a deterministic, separately identified tabular derivative before profiling. The layer profiles structure, timestamps, signal identity, units, per-signal quality, and evidence of configuration boundaries; records human mapping and unit decisions; emits independent trust dimensions and an analysis-readiness decision; and creates a canonical dataset for the existing baseline or SII workflow.

The layer is deterministic rules-based software. It does not add a second behavioral engine. SII continues to perform behavioral analysis only after this boundary.

## Trust philosophy

- Raw facts, inferred meaning, transformations, quality findings, review decisions, and analytical eligibility are different records.
- Absence of evidence is not positive evidence. A plausible tag name is not enough for a specific physical mapping.
- Physical behavior that is unusual is not automatically bad data.
- Missing periods are not silently interpolated. Invalid values are not silently replaced. Timestamp ordering changes and exclusions are recorded.
- Trust is multidimensional. No percentage or weighted aggregate represents overall data trust.
- A limited dataset may support some methods while blocking others. The readiness contract states those limitations directly.

## Canonical dataset boundary

The ingestion layer emits `historical-ingestion-trust/v1` records and `historical-canonical-dataset/v1` row artifacts. The canonical artifact is the only historical-data representation handed to new baseline and comparison analysis in this workflow.

Each canonical row contains:

- its original source row number;
- a canonical timestamp only when the selected source timestamp is parseable;
- the original timestamp text;
- all original source-column values plus per-signal original values;
- converted values only where a supported unit decision is sufficiently certain;
- explicit inclusion or exclusion state and reasons.

Each canonical signal has a stable ID derived from its normalized source identity, source-column position, and confirmed semantic role. Unused raw columns remain in the source schema and signal profiles even when they are excluded from analysis.

The `dataset_identity` is a SHA-256 digest over the raw-source digest, canonical schema version, deterministic rule versions, and normalized confirmed review decisions. Actor names and wall-clock review times do not affect identity. Identical input and identical decisions therefore reproduce the same identity and canonical content.

## Raw source preservation

The received bytes are immutable. The upload SHA-256 digest is computed before parsing. A content-addressed local source artifact is created with exclusive-write semantics; deployments with shared object storage also create a scope- and dataset-namespaced, content-addressed raw artifact before the temporary upload-transport object is removed. Neither durable raw artifact is overwritten by review or reprocessing.

Derived records reference the raw digest, byte count, original filename, opaque storage reference, tenant/workspace scope, and parser version. Trust APIs expose provenance metadata but never return the raw bytes, local paths, object-store credentials, or presigned URLs.

## Transformation provenance

Every derived change is an entry with a stable transformation ID, type, source field, rule/version, reason, affected rows or signal, and before/after unit where relevant. V1 transformations are limited to:

- deterministic JSON-to-tabular projection for existing JSON telemetry shapes, with both input and output digests;
- parsing a supported timestamp;
- representing an aware timestamp in UTC;
- deterministic ordering for the analysis view, when required, while retaining source row numbers;
- supported unit conversion;
- exclusion from analytical use;
- applying a recorded human mapping or unit decision.

Missing telemetry remains missing. Canonical artifacts contain no implicit interpolation, forward fill, sentinel substitution, smoothing, anomaly removal, or destructive correction.

## Timestamp rules

All columns are evaluated as timestamp candidates using name evidence and observed parse success. Candidate profiles expose parse counts, formats, timezone evidence, and selection reasons. A timestamp is selected only when the evidence has a deterministic winner; close candidates remain an explicit ambiguity.

Timestamp profiles record:

- selected column and alternatives;
- formats observed;
- timezone-aware, timezone-absent, mixed, and ambiguous counts;
- invalid, missing, and impossible values;
- source-order monotonicity, duplicates, negative clock jumps, and repeated blocks;
- interval distribution, median interval, irregularity, and large gaps;
- first/last time, gross coverage, gap burden, and effective usable coverage;
- integrity level `high`, `medium`, `low`, or `unavailable`, with reasons.

Aware timestamps are converted to UTC using their explicit offsets. Naive timestamps remain naive and carry a timezone limitation; v1 never assumes a site timezone. Major gaps are not interpolated. Duplicate or malformed timestamp rows may be excluded from time-dependent analysis, with source-row evidence preserved.

## Signal mapping rules

Mapping evidence can include the source header/tag, description and unit metadata when supplied, explicit engineering-unit tokens, observed type/range/cardinality/temporal behavior, strong existing canonical-role rules, and already-confirmed equipment identifiers. Correlation can support an alternative but cannot establish physical meaning by itself.

Supported roles include existing generic process/context roles and `flow`, `pressure`, `differential_pressure`, `temperature`, `return_temperature`, `supply_temperature`, `power`, `energy`, `valve_command`, `valve_position`, `pump_status`, `equipment_state`, `speed`, `frequency`, `setpoint`, `demand`, `load`, and `environmental_temperature`.

Every signal record includes the source identity, proposed role, confidence level, supporting reasons, conflicting evidence, alternatives, mapping state, and review requirement. Mapping states are `confidently_mapped`, `provisionally_mapped`, `ambiguous`, `unresolved`, and `excluded`. A generic `process_variable` role is permitted for numeric, headerless data because it makes no physical claim; the limitation travels with the data. Ambiguous and unresolved signals are not forced into methods that require semantic meaning.

## Unit rules

V1 recognizes explicit evidence for °F/°C, psi/kPa/bar, GPM/L/s/L/min/m³/h, W/kW/MW, percent/fraction, RPM/Hz, and existing energy units. Header metadata and consistent value suffixes are evidence. Numeric magnitude by itself is never sufficient.

Canonical units are °C, kPa, L/s, kW, kWh where supported, percent, RPM, and Hz. Each conversion records original unit, inferred unit, canonical unit, formula identifier/version, confidence, warnings, and original and converted values. Conflicting header/value units remain unresolved and are not converted. Dimensionally inconsistent role/unit combinations are warnings and require review.

## Data-quality rules

Per-signal profiles record missingness, longest dropout, valid/invalid/non-finite/nonnumeric counts, unexpected string states, cardinality, range and distribution, stuck/near-constant runs, clipping/saturation evidence, reset-like decreases, noise indicators, discontinuities, duplicate/nearly-duplicate candidates, sample volume, temporal coverage, and relationship-analysis fitness.

Rules are conservative. A range outside a broad physical plausibility bound is reported as `physically_unusual`; it is not automatically classified as sensor corruption. `insufficient_for_analysis` is reserved for evidence such as extreme sparsity, inadequate samples/coverage, nonnumeric contamination, unresolved identity needed by a method, or an exact duplicate selected for exclusion. Findings expose thresholds and source evidence.

Duplicate discovery uses value fingerprints first and bounded comparison within compatible role/unit buckets; it does not perform an unbounded all-signal pair scan.

## Exclusion rules

Exclusion is explicit at row and signal level. V1 may exclude:

- a malformed row from the canonical analytical view;
- a row lacking the chosen timestamp from time-dependent analysis;
- a duplicate timestamp/equipment record after preserving the first source occurrence;
- a signal explicitly excluded by a reviewer;
- a signal with no usable numeric/state data;
- an exact duplicate channel designated as redundant;
- a signal whose quality is demonstrably insufficient for the requested method.

An unusual value, weak name similarity, large gap, or possible configuration change alone does not authorize destructive removal. Every exclusion has a code, reason, rule version, and evidence reference.

## Uncertainty handling

Uncertainty is first-class. Alternatives and conflicts remain in the record. Provisional mappings and unresolved units can support unit-independent/generic methods only when the readiness contract names that limitation. Methods needing physical meaning or converted units must ignore them. Human decisions supersede only the field decided; they do not erase original machine evidence.

## Equipment and configuration awareness

V1 reports `no_configuration_concern_detected`, `possible_configuration_boundary`, `explicit_configuration_boundary`, or `insufficient_evidence`. The deterministic v1 detector uses included equipment/mode/staging state transitions and durable setpoint steps. It reports insufficient evidence when no eligible context signal exists rather than claiming consistency from process values alone.

The layer does not infer root cause or topology and does not silently segment a baseline. Boundaries include timestamps/source rows, involved signals, reason, confidence, and required downstream handling. Possible or explicit boundaries produce readiness limitations and require mode-aware or separately reviewed downstream handling.

## Human review model

The review UI summarizes all signals and surfaces only actionable uncertainty: ambiguous/unresolved mappings, unresolved or conflicting units, exclusions, duplicate candidates, timestamp concerns, configuration boundaries, and significant quality warnings. High-confidence items remain inspectable but do not require action.

For a signal, an operator can accept the proposal, select a supported role, leave it unresolved, or exclude it. Supported units can be confirmed or corrected. Each decision records actor, UTC time, previous state, requested state, and decision source. Reprocessing creates a new immutable derived revision; it never edits raw data or prior review history.

## Trust dimensions

The trust summary contains separate dimensions for timestamp integrity, semantic mapping confidence, unit confidence, missing-data burden, signal-quality fitness, operating-state coverage, configuration consistency, and analysis readiness. Every dimension contains a qualitative status, reasons, evidence references, limitations, and any remediation/review requirement. Dimensions are never averaged.

## Analysis readiness

Readiness is one of:

- `ready`: sufficient eligible canonical data with no material carried limitation;
- `ready_with_limitations`: analysis can run, but listed methods/signals/periods are constrained;
- `review_required`: focused decisions can make a currently blocked analytical path usable;
- `insufficient_trustworthy_data`: the source cannot currently support the requested analysis.

The result lists included/excluded signals, limitations, blocked methods, timestamp blockers, unresolved reviews, operating coverage, and exact minimum-data reasons. It is not a percentage. Downstream analysis must accept the included canonical signal set and limitations rather than reinterpreting raw columns.

## Deterministic behavior

Rule tables, parse formats, canonical units, thresholds, fingerprint algorithms, schema versions, and conversion formulas are versioned constants. Stable ordering is used for signals, evidence, warnings, decisions, and serialized rows. Current time, randomized sampling, process identity, and dictionary/set iteration order are excluded from dataset identity.

## Persistence and isolation

Trust records use the existing dataset-scope abstraction and scoped local/shared state. Canonical and raw artifact references are namespaced by the opaque scope storage ID. Reads verify tenant, user, workspace, and dataset identity. No tag, mapping, unit decision, or convention is shared across scopes. There is no cross-tenant learned model in v1.

Raw, trust, review, and canonical records have distinct object names. GET operations are pure: they do not repair, migrate, recalculate, or write state.

## API contracts

The versioned API is intentionally small:

- `GET /api/data/ingestion/v1/datasets/{dataset_id}` returns the ingestion profile, timestamp and signal profiles, trust dimensions, review queue, configuration assessment, canonical metadata, and readiness.
- `GET /api/data/ingestion/v1/datasets/{dataset_id}/canonical` returns a bounded page of canonical rows and provenance.
- `PATCH /api/data/ingestion/v1/datasets/{dataset_id}/review` records strict mapping/unit/exclusion decisions and deterministically rebuilds the derived revision.

Reads require API access. Review writes require operator access. IDs and request bodies are bounded, unknown fields are rejected, operation IDs are stable, and the current authenticated dataset scope is mandatory.

## Frontend workflow

The existing Data upload workflow becomes:

`Upload → Profiling → Review only what needs attention → Ready for analysis → Analyze`

The review surface leads with counts and readiness, then provides focused sections for required mapping/unit decisions, exclusions/duplicates, timestamp concerns, configuration evidence, and quality limitations. Plain operator language is paired with technical details on demand. Controls are keyboard accessible, status changes use live regions, and the layout collapses to a single column on mobile.

## Downstream analysis contract

Baseline and comparison workflows receive canonical analysis rows, stable canonical signal IDs, included-signal metadata, timestamp profile, configuration boundaries, trust limitations, and the canonical dataset identity. SII must not read excluded raw columns or apply a second unit inference. Evidence Packages include the raw-source digest/reference, canonical dataset identity, ingestion schema/rule versions, included/excluded signal IDs, transformations, review revision, readiness outcome, and carried limitations.

Legacy saved uploads remain readable. Uploads processed before this contract can be labeled `legacy_unprofiled`; they are not retroactively represented as trusted v1 data without deterministic reprocessing from an available raw source.

## Security

The layer preserves existing authentication, role authorization, upload-size limits, filename/path validation, queue ownership, API/worker separation, tenant/workspace scope, and storage abstraction. Raw bytes and canonical row values are never logged. API responses do not reveal storage filesystem paths or object-store credentials.

## Performance

Profiling is streaming and linear in row count times signal count. Per-signal bounded samples support robust statistics. Correlation-based semantic alternatives compare uncertain signals against at most eight strong anchors and stop at a global comparison limit; they never promote a mapping. Duplicate-channel detection groups fingerprints and uses bounded comparisons within compatible buckets rather than an unbounded all-pairs scan. Analysis sampling is deterministic, bounded by both row count and canonical cell count, and separately disclosed from population counts. Benchmarks report raw preservation, parsing, schema/timestamp profiling, mapping, quality, normalization, persistence, total wall time, and peak memory.

## Non-claims

V1 does not diagnose cause, certify sensor calibration, prove a tag's physical identity, infer physical topology, determine a safe operating envelope, predict failure, or authorize equipment/control action. `ready` means fit for the declared Neraium analytical methods under listed assumptions; it does not mean the source is complete or correct in every physical sense.

## Deferred capabilities

V1 deliberately excludes autonomous causal diagnosis, hidden customer-specific or cross-tenant mapping models, automatic CMMS reconciliation, opaque AI confidence, automatic destructive repair, topology inference from tag names, silent major-gap interpolation, automatic removal of unusual behavior, and LLM-only semantic truth. Implicit seasonal segmentation, signal-availability regime detection, and multivariable change-point discovery are deferred; v1 does not present those as configuration facts. Probabilistic or language-model mapping may be added later only as advisory, provenance-tracked, bounded, tenant-isolated evidence requiring deterministic validation or review.
