# Evidence Package v1 architecture

## Product and canonical ownership

An Evidence Package is a versioned, auditable record of a persistent system behavior change, its known operating context, its supporting telemetry, the limitations of that evidence, and the most defensible next investigative information. In v1 the package formalizes only values already produced by the comparison engine.

The completed upload result remains the canonical persisted analysis record. Its single embedded `evidence_package` replaces the comparison finding as the canonical finding representation; legacy finding fields are a one-way serializer projection from the package. Existing evidence-run records remain operational/export artifacts rather than another Evidence Package source of truth. Findings were previously JSON embedded in completed upload results (sometimes repeated under `conditions`, `analysis_result`, and explanation compatibility containers), not relational finding rows.

## Existing end-to-end path

1. Baseline uploads build and persist a versioned Behavioral Digital Model through `behavioral_model_repository`, including tenant/workspace, source dataset, system, version, and activation state.
2. Comparison upload intake binds the exact active model and rejects baseline, portfolio, system, or comparison-dataset mismatches.
3. Existing relationship code calculates correlation drift; v1 does not change its thresholds or mathematics.
4. Analysis explanations and condition corroboration construct the visible finding.
5. Upload evidence converts the same result into an operational evidence-run/export record.
6. Upload completion persists the entire completed result as scoped JSON in local/shared object storage and writes scoped analysis lookup indexes.
7. Replay generation remains in the upload pipeline and its persisted timeline/frame count is only referenced by package evidence.
8. Data routes serialize exact stored analysis results. Package endpoints use explicit Pydantic response models rather than ORM serialization.
9. The frontend restores `/analyses/:id` through the existing exact-analysis route; the embedded package survives the same normalization and refresh path without a page redesign.
10. `DatasetScope` attaches and validates tenant (`organization_id`), workspace/portfolio, system, baseline, and dataset identity. Package lookups use the same scope-prefixed indexes.

Canonical models are therefore JSON Behavioral Digital Models, completed upload/analysis JSON results, embedded findings/evidence, scoped analysis indexes, replay timeline JSON, and runtime-SQLite evidence/audit records. Accounts are runtime-SQLite authentication records; portfolio ownership is the current scoped workspace identity.

## Schema

`evidence-package-v1` contains stable identity and scope, lifecycle classification, one structured primary relationship, an exact comparison reference, five confidence dimensions, ordered timeline and evidence collections, empty-safe limitations and hypotheses, and provenance. Lifecycle values are `emerging`, `active`, `escalating`, `stable_persistent`, `dormant`, `load_dependent`, `monitoring_after_intervention`, `resolved`, `superseded`, and `insufficient_evidence`. The current persistent comparison maps to `active`.

Comparison reference values are `matched_historical_baseline`, `related_state`, `physics_informed_envelope`, and `insufficient_evidence`; only the first has analytical behavior in v1. Confidence dimensions are finding, data quality, operating state, mapping, and physical consistency. Each has a `high`, `medium`, `low`, or `unknown` level, nullable score, reason, method, and evidence references. Unsupported dimensions are explicitly `unknown`; the old generic confidence is not reinterpreted.

Evidence ordering is deterministic: baseline strength, comparison strength, absolute change, both sample counts, persistence when available, exact baseline identity, and replay count/availability. A timeline event is emitted only when the existing result contains a defensible onset and calls it the “earliest supported deviation.” Limitations and hypotheses remain empty unless real metadata exists.

## Persistence, revision, and migration

The package is embedded in the canonical completed result and has a deterministic UUIDv5 plus stable human-readable number. A scoped package-ID lookup record points back to the owning analysis; it does not duplicate finding content. Revision 1 is immutable in this phase. The existing append-only runtime audit-event facility is the selected audit mechanism for future important updates; GET requests are pure and never write or increment revisions.

No destructive relational migration is required because canonical analyses/findings are scoped JSON rather than relational rows. New comparisons persist packages during normal completion. Pre-v1 analyses remain readable unchanged; on serialization, a deterministic package is derived in memory only when the result explicitly records the persisted baseline model used for drift and that identity matches the selected baseline. This lazy compatibility path performs no backfill and repeated reads yield byte-equivalent content. Old results lacking that proof or a stable persisted completion timestamp retain their legacy response without a fabricated package.

## API and compatibility

* `GET /api/data/analyses/{analysis_id}` returns the existing result with `evidence_package` when supportable.
* `GET /api/data/analyses/{analysis_id}/evidence-package` returns the explicitly validated package.
* `GET /api/data/evidence-packages/{package_id}` resolves the exact package through a tenant/workspace-scoped lookup.
* `GET /api/data/analyses/{analysis_id}/findings` retains the legacy contract, projected one-way from the canonical package while preserving existing presentation fields.

Collections have stable construction order, schema enums are validated, and all access follows existing dataset-scope isolation.

## Known limitations and deferred phases

V1 does **not** implement physics-informed consistency envelopes, semantic topology inference, adaptive operating-state clustering, propagation reconstruction beyond currently available onset evidence, ranked operational hypotheses, package merging or splitting, recurrence tracking, engineer disposition feedback, CMMS integration, or M&V calculations. It also does not infer severity, diagnoses, missing sensors, calibration state, or confidence scores that the engine does not calculate.

## Timeline and Earliest Supported Deviation v1

### Architecture and persisted timing audit

The Evidence Package already had an ordered `TimelineEvent` collection and package-level `first_supported_at`, `last_observed_at`, completion, and evaluation timestamps. Before this phase, however, the builder emitted only an optional earliest-supported event from an existing finding onset. Completed comparisons persist `completed_at` (or the legacy `last_processed_at` fallback), exact baseline/comparison identity, relationship statistics and optional `persistence_score`. Operating Context v1 optionally persists baseline and comparison window bounds. Replay is persisted as a timeline plus frame-count metadata and is already represented by the deterministic `ev-replay` reference. Supporting evidence already records relationship strengths, change, sample counts, persistence, baseline identity, replay availability, data quality, and operating-context facts.

Timeline v1 uses only those completed-analysis fields. It adds no database table, migration, upload read, raw-file read, or new persistence mechanism. Replay remains supporting evidence and is not copied into the Evidence Package timeline.

### Philosophy and earliest supported deviation

The timeline answers: **when is the earliest timestamp for which the persisted comparison evidence supports this behavioral change?** It does not claim when a physical problem, degradation, or failure began. An `earliest_supported_deviation` event is emitted only when the persisted finding has a valid timezone-aware onset within the persisted comparison window (when window bounds are available). Its evidence references point to already persisted comparison statistics, samples, persistence, and comparison-window evidence.

When no valid persisted onset exists, or an onset falls outside the known comparison window, `first_supported_at` remains null and an `unknown` event states the reason. The unknown event's timestamp is the persisted comparison completion/evaluation time; it records when the unknown determination was made and is not a substitute onset. Baseline start, comparison start, and first replay/sample timestamps are never promoted to earliest support.

### Event ordering and compatibility

Supported events are `comparison_started`, `earliest_supported_deviation`, `behavior_persisted`, `supporting_relationship_change`, `comparison_completed`, and `unknown`. Comparison start requires a persisted comparison-window start. Continued persistence requires both persisted persistence evidence and the comparison-window end. Completion uses the persisted completed-analysis timestamp. Additional relationship-change events are not emitted unless future persisted outputs explicitly support their timing.

Events are sorted by parsed UTC timestamp, then a fixed semantic tie-break order, then event type. Sequence numbers and event IDs are assigned only after sorting. Timestamps are normalized to UTC, and generation uses no wall clock, random identifiers, or raw telemetry reads. Repeated package GETs therefore preserve deterministic timeline content, package identity, routes, and the `evidence-package-v1` schema version.

Temporal order means only “observed before/after.” It never means upstream/downstream, cause/effect, precursor/responder, propagation, topology, or root cause. Those capabilities, including causal inference, propagation, topology, hypotheses, recurrence, lifecycle expansion, feedback, and governance, remain deferred roadmap work.

## Evidence Limitations v1

### Purpose and evidence philosophy

Evidence Limitations answer **“What prevents a stronger conclusion?”** They do not lower or restate confidence, repeat the timeline, propose a hypothesis, or diagnose equipment. A limitation is included only when a completed, persisted comparison output directly demonstrates the boundary. The absence of evidence about a possible limitation is treated as unknown and produces no limitation. This preserves the product doctrine that evidence precedes conclusions, unknown is valid, and limitations are evidence rather than weaknesses.

Uncertainty and limitation are distinct. A confidence dimension records how strongly a defined result is supported and may remain `unknown` when no calculation exists. A limitation records a specific, evidenced reason why the package cannot support a stronger interpretation. Consequently, an unknown confidence value alone never generates a limitation.

### Supported deterministic generation

The v1 builder recognizes only these persisted facts:

* an explicitly null operating-context input records missing operating-state evidence;
* an Operating Context result whose process-demand comparability is `unknown` records unavailable comparable conditions;
* a persisted signal catalog missing a supporting signal's canonical role records missing semantic mapping; exact signal identity is resolved from `source_column`, then `column`, then a dictionary catalog key, without display-name or normalized-label guessing;
* a non-empty persisted `telemetry_ambiguity` result records telemetry ambiguity;
* two or more alternatives retained on the persisted finding record that multiple explanations remain plausible; and
* a persisted physics-reasoning status of `unavailable`, `not_available`, or `not_implemented` records unavailable physics validation.

Each generated item has a stable ID, title, description, reason, category, severity, active status, and references to structured supporting evidence in the same package. Limitation existence and limitation severity are independent: v1 evidence supports existence only, so every automatically generated limitation has `severity: unknown`. `low`, `medium`, and `high` are reserved for future explicitly documented and persisted severity evidence; category, confidence, and wording are never used to infer severity. Construction follows a fixed rule order and uses no clock, randomness, raw telemetry reads, or GET-time writes. Repeated generation and repeated GET therefore preserve package identity, schema version, revision, collection order, and byte-equivalent JSON content.

### Unsupported situations and deferred work

A missing legacy key is not reinterpreted as proof that a capability was unavailable. V1 also does not derive limitations merely from unknown confidence, low confidence, an absent onset, an empty replay, a missing topology, generic prose, or a capability that the completed result never evaluated. It does not invent missing sensors, environmental requirements, post-change sufficiency thresholds, causal ambiguity, or physical explanations.

Hypotheses, diagnoses, propagation, topology construction, lifecycle and recurrence logic, engineer feedback, governance, post-intervention validation, adaptive models, and a physics engine remain deferred. Evidence Limitations v1 only exposes boundaries already supported by persisted evidence and does not begin any of those roadmap phases.
