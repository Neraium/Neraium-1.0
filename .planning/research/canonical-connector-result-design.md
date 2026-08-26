# P0.1 Canonical Connector Result — Implementation Design

Date: 2026-08-26
Status: design gate; no analytical semantics change.

## Decision summary

Persist exactly one canonical, compressed, immutable `AnalysisWindowExecution` artifact in the existing PostgreSQL `telemetry` authority. Its SHA-256 digest is computed over deterministic uncompressed canonical JSON. Artifact insertion and the claimed analysis-window transition to `completed` occur in one database transaction. All customer presentation is a bounded projection rebuilt from that verified artifact without calling SII.

This design does not change SII math, thresholds, finding classification, suppression, persistence qualification, Phase 4 learning, source routing, AWS, or deployment. It implements P0.1 only.

## Canonical authority and identity

### Authoritative payload

The canonical payload is the JSON-normalized value of `AnalysisWindowExecution.as_dict()`:

- actual `contract_version` (`analysis-window-execution.v1`);
- terminal status;
- analysis window ID;
- connector source kind and source ingestion run ID;
- complete `sii_result` exactly as returned by the one engine invocation;
- complete canonical `analysis_result` exactly as built from that engine output;
- bounded connector lineage summary.

Exact observation membership remains authoritative in `telemetry.analysis_window_observations`, referenced through the window ID and proven by the artifact's observation count/lineage digest. The artifact does not duplicate all observation rows.

### Serialization and digest

- JSON normalization uses sorted keys, compact separators, UTF-8, `ensure_ascii=False`, and rejects NaN/Infinity.
- SHA-256 is computed over the uncompressed canonical UTF-8 bytes.
- The canonical bytes are compressed once with deterministic zlib encoding for PostgreSQL `BYTEA` storage.
- Retrieval decompresses, verifies byte count and SHA-256 before JSON parsing, then validates identity/version fields against indexed columns.
- The digest in `analysis_windows.result_digest` becomes this full-artifact digest. It no longer represents only reduced metadata.

The maximum uncompressed canonical artifact is 256 MiB. This is an operational persistence bound above the audit's approximately 161.9 MB maximum measured result, not an analytical threshold. Oversize or unserializable results fail artifact persistence and cannot claim retrievable completion; they are never truncated.

### Stable result ID

`result_id` is UUIDv5 over:

- artifact contract version;
- deterministic analysis window ID;
- execution contract version.

The window identity already binds tenant resource/facility scope, connection, source run, system, optional asset, analysis bounds, and authority digest. Therefore the same exact window/contract always resolves to one result ID. A legitimate new run or contract identity produces a distinct window or result identity; repeated execution cannot create divergent artifacts.

## Additive storage model

Create forward-only migration `005_persist_canonical_analysis_results` depending on migration `004`.

### `telemetry.analysis_result_artifacts`

| Column | Purpose |
|---|---|
| `id UUID PRIMARY KEY` | Stable canonical result ID |
| `tenant_scope_id`, `workspace_id`, `resource_scope_id`, `facility_id` | Full server authority |
| `analysis_window_id UUID` | One-to-one immutable window owner |
| `connection_id UUID` | Explicit source scope for retrieval |
| `source_ingestion_run_id UUID` | Exact trigger run |
| `system_id TEXT`, `asset_id TEXT` | Exact physical scope |
| `window_start`, `window_end` | Exact analysis bounds |
| `authority_digest TEXT` | Exact mapping/system authority |
| `artifact_schema_version TEXT` | New artifact format, distinct from engine/result versions |
| `execution_contract_version TEXT` | Actual execution contract |
| `analysis_schema_version TEXT` | Actual top-level analysis `schema_version` |
| `analysis_contract_version TEXT` | Actual nested `analysis_metadata.contract_version` |
| `engine_name`, `engine_version` | Actual supplied SII engine identity |
| `reference_metadata JSONB` | Bounded actual model/baseline/snapshot/reference fields with source paths; absent values remain absent; maximum 32 KiB |
| `observation_count`, `observation_lineage_digest` | Exact membership proof referencing normalized joins |
| `finding_ids`, `evidence_ids` JSONB | At most 256 exact generated IDs each plus totals/truncation flags; combined maximum 64 KiB |
| `payload_encoding` | `zlib+canonical-json.v1` |
| `payload_digest` | SHA-256 of uncompressed canonical bytes |
| `payload_uncompressed_bytes`, `payload_stored_bytes` | Payload measurements |
| `serialization_ms` | Completion measurement |
| `payload BYTEA` | Single authoritative compressed artifact |
| `created_at` | Immutable publication time |

Constraints and indexes:

- unique full-scope `analysis_window_id` and one artifact per window;
- foreign keys to the exact scoped analysis window and source ingestion run with `ON DELETE RESTRICT`;
- connection/run/window identity must agree with the referenced rows;
- digest format, byte counts, JSON object type/size, and window-range checks;
- scoped indexes for `(resource_scope_id, facility_id, connection_id, source_ingestion_run_id, created_at)` and `(resource_scope_id, facility_id, system_id, COALESCE(asset_id,''), window_start DESC)`;
- database triggers reject every `UPDATE` and `DELETE` on completed artifacts.

Ordinary application code has no artifact deletion path. A future legally required tenant-retention teardown must be an explicit audited migration/administrative operation that first exports or records the governed disposition; it is intentionally outside P0.1. Application rollback does not delete artifacts.

The migration is idempotent, advisory-lock protected, version-ledgered, additive, and forward-only. The application readiness verifier requires migration 005 before enabling the telemetry runtime. No migration is run by this task.

## Actual version and reference identity

Persist the following distinctly:

- artifact schema: `telemetry-canonical-result-artifact.v1`;
- execution contract: actual `execution.contract_version`;
- analysis result schema: actual `analysis_result.schema_version`;
- analysis result contract: actual `analysis_result.analysis_metadata.contract_version`;
- engine name/version: actual `sii_result.engine.name/version`;
- SII schema version only if the engine actually emits one (current engine does not);
- model ID/version and snapshot IDs from actual `behavioral_model` / `behavioral_snapshots` output;
- baseline/reference identity only where actual fields are emitted.

The current durable-lineage lookup of `analysis_result.contract_version` is replaced with the actual top-level `schema_version`, and the nested contract is recorded separately. Missing values cause a bounded version-mismatch event and persistence failure only when a contract that must be present for this artifact format is missing; optional engine/reference identities are not invented.

## Completion, failure, and recovery semantics

### Normal completion

1. Run SII exactly once and construct `AnalysisWindowExecution`.
2. Canonically serialize, size-check, hash, compress, and build bounded indexed metadata.
3. In one repository transaction:
   - insert the immutable artifact with `ON CONFLICT DO NOTHING`;
   - lock/read any existing artifact and compare every scoped identity, version, digest, and byte count;
   - reject a divergent existing artifact as an identity conflict;
   - compare-and-swap the claimed window from `running` to `completed`, recording the artifact digest/ID metadata;
   - commit.
4. Return the execution to the current caller as today.

### SII succeeds but artifact persistence fails

The window cannot claim product-retrievable completion. The service emits `telemetry_canonical_result_persistence_failed`, attempts the existing claimed transition to terminal `failed` with a bounded reason code, and returns/raises failure. Raw result content is never logged. Retrieval returns opaque not-found because no canonical authority exists.

### Artifact persists but presentation projection fails

Projection is outside the canonical commit and never mutates the artifact. Retrieval verifies and returns the artifact identity even if bounded projection construction fails; it emits `telemetry_canonical_result_projection_failed`. A later request can rebuild the projection from the artifact without SII. No canonical data is removed or rewritten.

### Worker dies after artifact persistence but before status update

The production transaction makes this externally unobservable: artifact and completed status commit together or both roll back. Repository idempotency still accepts an identical pre-existing artifact during recovery/testing and rejects divergence. If a database/operator repair ever exposes an artifact beside a non-completed window, the scoped recovery method may finalize only after verifying exact identity/digest and must call SII zero times.

### Repeated job execution

A completed window returns the existing result identity without SII. An identical artifact insert is idempotent. A different digest for the same result/window identity is a hard conflict and never overwrites the original.

### Legacy completed windows

Existing rows without an artifact remain historical status/lineage records but are not retrievable as exact results. The product returns unavailable; it never reruns SII or reconstructs a close approximation.

## Authorized retrieval API

Extend the existing `data-connections` API family rather than creating an unrelated public family.

### List bounded result identities for one exact run

`GET /api/data-connections/{connection_id}/runs/{source_run_id}/analysis-results`

- server derives tenant/workspace/resource/facility from authenticated explicit workspace membership;
- verifies the connection and source run belong to that scope and each other;
- returns bounded result summaries only (result/window ID, system/asset, window, state, counts, actual versions/digest, byte counts);
- never implements an unscoped latest lookup.

### Retrieve and project one exact result

`GET /api/data-connections/{connection_id}/runs/{source_run_id}/systems/{system_id}/analysis-results/{result_id}?asset_id=...`

- SQL filters all four scope fields plus connection, source run, system, null-safe asset, and result ID;
- wrong tenant, workspace/facility, connection, run, system, asset, or result ID returns the same opaque 404;
- artifact ID alone is never accepted;
- retrieval decompresses and validates digest, byte count, execution/window/run identity, and version agreement;
- the response contains bounded artifact metadata and `product_result`, derived from the exact artifact;
- retrieval invokes SII zero times.

### Verify and page exact observation lineage

`GET /api/data-connections/{connection_id}/runs/{source_run_id}/systems/{system_id}/analysis-results/{result_id}/lineage?asset_id=...&limit=...&cursor=...`

- applies the identical full scope/connection/run/system/asset/result predicate;
- reads `analysis_window_observations` joined to scoped immutable observations in deterministic observation-ID order;
- recomputes the full membership count and lineage digest and compares both with artifact metadata before returning any page;
- returns exact lineage identities and timestamps in pages of at most 100, plus total count, verified digest, and an opaque continuation cursor;
- never duplicates raw provider payloads, secrets, or the full observation corpus into the result artifact.

The ordinary result response reports `lineage_verified=true` only after this scoped database verification succeeds. A mismatch fails closed and emits a version/integrity event.

The endpoint records bounded retrieval latency and projection bytes. It never logs or echoes raw telemetry or the full SII artifact as part of ordinary product transport.

## Depth-specific bounded product projections

The exact stored `analysis_result` is not transported directly: connector normalization currently expands up to 5,000 rows x 64 signals into as many as 320,000 normalized records. The server instead derives explicit DTOs from the verified artifact.

### Shared result envelope (maximum 1 MiB)

- `result_id`, `analysis_id`, `analysis_window_id`, source run, connection, system, asset, and window bounds;
- artifact digest/contract, actual analysis schema/contract, engine/reference identities, lineage count/digest/verification state;
- exact conditions, insights, relationships, systems, executive summary, fingerprint, recommendations, warnings/errors, evidence index, and bounded `sii_evidence` from `analysis_result`;
- normalized-telemetry summary, tag catalog, and signal catalog, but never `normalized_telemetry.records`; exact observation membership is referenced by result/window and served through verified lineage pagination;
- `source_type=telemetry_connector`, terminal availability/status, and the read-only product boundary.

Hard bounds: at most 64 signal catalog entries, 256 finding/evidence IDs, 128 evidence-index entries, 32 systems/relationships/conditions/insights/recommendations each, 32 warnings/errors each, strings at most 4 KiB, JSON nesting at most 16, total serialized envelope at most 1 MiB. If an existing analytical collection exceeds transport bounds, the DTO carries exact selected items, original count, truncation flag, and canonical artifact/source path; it never changes the artifact or analytical classification.

### Technical channel projection (maximum 2 MiB)

Existing Investigation/Evidence panels currently read selected direct SII paths. The server supplies a bounded `sii_result` transport projection at those same paths so the screens do not change semantics:

- relationship graph/change facts;
- temporal state/correlation/MI/lag/variance/entropy/regime facts;
- covariance/multivariate summaries;
- multiscale facts;
- persistence and uncertainty;
- expected behavior, behavioral evolution, propagation, snapshots, and model identity;
- physics reasoning/evidence when actually present;
- data conditions, sensor health, processing trace, and provenance/version facts.

Each channel permits at most 32 list items, 128 mapping entries, 4 KiB strings, nesting depth 16, and 256 KiB serialized bytes. Each carries exact `source_path`, original item/byte counts, truncation state, and the canonical result ID/digest. The combined technical transport is at most 2 MiB. Facts are selected, never recalculated or summarized into new analytical claims.

### Evidence audit metadata (maximum 256 KiB)

Evidence Record receives every exact ID/version/digest, window/timestamp, finding-owned metric/relationship, classification/confidence/limitation, and reference/lineage metadata needed for audit. Large module bodies remain referenced to the immutable artifact and their bounded channel DTO. Exact observation membership is available through verified pagination/export, not copied into this DTO.

Projection byte caps are enforced after canonical serialization. Projection failure never mutates the artifact and is retryable without SII. A future optional projection cache may be added only as a rebuildable versioned sidecar.

## Product routing without screen redesign

### Data connection entry

Completed/partial ingestion runs receive a `Review results` action. It first requests the exact run's bounded result identities. If the run produced multiple system/asset windows, the existing run row shows each bounded identity; selecting one calls the exact scoped retrieval endpoint.

The frontend keeps the returned `product_result` as the active completed analysis result and navigates to the existing engineering workspace. It does not write it into historical-upload `latest` authority and does not refetch/rerun SII.

### Results

Existing `buildEngineeringReasoningModel` consumes `product_result.analysis_result`; existing `projectResults` remains the triage allowlist. No technical module payload is added to Results.

### Finding Review

Existing exact finding ID routing and `projectFindingReview` consume the original persisted conditions/insights and their original IDs. Workflow rows, if materialized, are bounded rebuildable projections keyed by original source finding ID; they never replace the artifact.

### Investigation

Existing `projectInvestigation` consumes the same active model and bounded SII evidence projection. Baseline/current, relationships, persistence, context, temporal/multivariate facts, source signals, data quality, and lineage appear only when present.

### Evidence Record

Existing `projectEvidenceRecord` consumes the same exact result identity, conditions, bounded SII evidence, lineage, versions, and digest metadata. It receives artifact/execution/analysis identities distinctly. Ordinary Evidence Record transport remains bounded; the full diagnostic SII payload stays in the canonical artifact.

For results with no real finding, the frontend uses the canonical `result_id` as an analysis route identity—not a finding ID—and invokes result-scoped `projectAnalysisInvestigation` / `projectAnalysisEvidenceRecord` adapters. These adapters show run-level state, supported technical channels, exact IDs/versions/digest, limitations, and verified lineage. They never create a condition, insight, workflow case, or finding-shaped compatibility object. Finding Review remains unavailable unless an actual persisted finding/condition ID exists.

Unknown finding IDs continue to fail closed through the existing exact projectors. All screens refer to the same `result_id`, analysis/window identity, digest, finding IDs, and lineage.

## Stable and insufficient states

- A stable/no-material-change artifact is completed, retrievable, and projected with the exact empty finding collection. Results renders the existing stable state; Review is unavailable, while result-scoped Investigation and Evidence Record load the real run-level evidence and audit identity without a fake finding.
- An insufficient-evidence artifact is completed and retrievable when SII produced that terminal analytical state. Results renders the existing insufficient state and limitations. Review appears only for a real insufficient analytical object; otherwise result-scoped Investigation/Evidence remain available. It is never transformed into a fake change finding or synthetic evidence observation.
- Pre-SII connector `ineligible` windows remain outside this artifact contract because no completed analytical result exists. P0.4, not P0.1, owns changes to that customer-state semantics.

## Rebuildable finding/evidence projections

The immutable artifact is the only analytical authority. For material results, an authorized product retrieval may idempotently materialize bounded `evidence_runs` / `finding_cases` projections using the original analysis result and original source finding IDs so existing team workflow remains available. Projection failure is non-authoritative and observable. Stable/insufficient results must not use compatibility fallbacks that synthesize `evidence-{run_id}` or `run-observation` findings.

## Observability

Add bounded structured events:

- `telemetry_canonical_result_persisted`;
- `telemetry_canonical_result_already_exists`;
- `telemetry_canonical_result_persistence_failed`;
- `telemetry_canonical_result_retrieved`;
- `telemetry_canonical_result_authorization_rejected`;
- `telemetry_canonical_result_version_mismatch`;
- `telemetry_canonical_result_projection_failed`.

Allowed log fields: event, result/window/run/connection IDs, system/asset IDs, status, contracts, digest prefix or full non-secret digest, byte counts, serialization/retrieval duration, error type/reason code. Prohibited: payload, raw telemetry, secret/configuration/provider bodies, evidence text.

## Acceptance and measurement plan

The binding restart test uses the real scheduler/ingestion/analysis path with deterministic telemetry and a durable repository backing shared across a newly constructed service/runtime instance. It discards every execution object and evaluator callback, then retrieves through the exact authorized path. A call counter asserts retrieval performs zero new SII executions.

Assertions cover:

- same window -> same result ID and artifact digest;
- exact canonical bytes/digest survive restart;
- wrong tenant/workspace/facility/connection/run/system/asset/result fails opaque;
- identical retry reuses; divergent retry conflicts;
- material, stable, and insufficient analytical outputs retain their exact finding collections/states;
- Results, Review when applicable, Investigation, and Evidence Record all carry the same result/window/finding/reference/lineage identity;
- persisted artifact facts exactly match product projections;
- actual analysis schema/contract is non-empty and correct;
- serialization, compression, artifact bytes, indexed metadata bytes, product projection bytes, and retrieval latency are reported.
- exact observation membership count/digest is recomputed from durable joins, and paginated lineage IDs match the artifact reference;
- shared result envelope <=1 MiB, each technical channel <=256 KiB, combined technical projection <=2 MiB, evidence audit metadata <=256 KiB.

## Deployment ordering and rollback

1. Apply migration 005 in each non-production environment through the existing controlled migration process.
2. Verify migration ledger, columns, constraints, indexes, triggers, and empty-table readiness.
3. Deploy application code that requires migration 005.
4. Observe persistence/retrieval/version/projection events before any broader rollout.

This task creates but does not apply the migration. Application rollback is safe because the additive table and artifacts can remain unused. Database downgrade is intentionally unsupported: dropping immutable result authority would be destructive. Existing historical/manual result paths remain unchanged throughout rollout.

## Explicit non-goals / P0.2+ dependencies

Not implemented here:

- P0.2 event-time authority for backfill/live learning;
- P0.3 single cross-product finding/reference authority;
- P0.4 insufficiency semantics changes;
- P0.5 suppression/persistence qualification changes;
- P0.6 upload facade removal;
- P1.1 cross-connection system windows/relevance routing;
- P1.2 internal 161 MB evidence/module-copy redesign;
- covariance, Phase 4 storage, temporal preprocessing, live-route, or analytical-method changes.

P0.1 deliberately creates the durable exact authority that later roadmap items may reference, while preserving every current analytical decision.
