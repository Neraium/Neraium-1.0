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

No destructive relational migration is required because canonical analyses/findings are scoped JSON rather than relational rows. New comparisons persist packages during normal completion. Pre-v1 analyses remain readable unchanged; on serialization, a deterministic package is derived in memory only when the old result contains enough exact comparison relationship data. This lazy compatibility path performs no backfill and repeated reads yield the same identity. Old results lacking that evidence retain their legacy response without a fabricated package.

## API and compatibility

* `GET /api/data/analyses/{analysis_id}` returns the existing result with `evidence_package` when supportable.
* `GET /api/data/analyses/{analysis_id}/evidence-package` returns the explicitly validated package.
* `GET /api/data/evidence-packages/{package_id}` resolves the exact package through a tenant/workspace-scoped lookup.
* `GET /api/data/analyses/{analysis_id}/findings` retains the legacy contract, projected one-way from the canonical package while preserving existing presentation fields.

Collections have stable construction order, schema enums are validated, and all access follows existing dataset-scope isolation.

## Known limitations and deferred phases

V1 does **not** implement physics-informed consistency envelopes, semantic topology inference, adaptive operating-state clustering, propagation reconstruction beyond currently available onset evidence, ranked operational hypotheses, package merging or splitting, recurrence tracking, engineer disposition feedback, CMMS integration, or M&V calculations. It also does not infer severity, diagnoses, missing sensors, calibration state, or confidence scores that the engine does not calculate.
