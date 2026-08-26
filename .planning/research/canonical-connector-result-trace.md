# P0.1 Canonical Connector Result — Production Trace

Date: 2026-08-26
Scope: P0.1 only; read-only trace completed before implementation.

The three requested audit artifacts were absent from this dedicated worktree. Their current-main copies were read from the adjacent `../Neraium-1.0-sii-audit-current/.planning/research/` worktree: `sii-current-power-efficiency-audit.md`, `sii-current-architecture-inventory.md`, and `sii-audit-delta-vs-pr107.md`.

## End-to-end production flow

1. `build_telemetry_runtime` wires the production `TelemetryScheduler` to `prepare_connector_page` and `process_ingestion_run` (`backend/app/services/telemetry_runtime.py:252-266`).
2. The scheduler claims scoped work, fetches through a retrieval-only provider, sends each page through `prepare_connector_page`, and atomically persists accepted canonical observations and the checkpoint (`backend/app/services/telemetry_scheduler.py:150-358`).
3. `prepare_connector_page` enforces approved signal mapping, source quality, timestamp/value validity, unit conversion, server-resolved facility/system/asset identity, and mapping authority before emitting canonical observations (`backend/app/services/telemetry_ingestion.py:625-935`).
4. `process_ingestion_run` reloads persisted observations for the exact connection/run, groups them by `(system_id, asset_id, mapping_authority_digest)`, selects rolling 24-hour windows, and calls `run_post_ingestion_analysis` (`backend/app/services/telemetry_analysis_service.py:592-694`).
5. `deterministic_analysis_window_id` binds the service contract, resource/facility scope, connection, source run, system, optional asset, window bounds, and authority digest into a stable UUIDv5 (`telemetry_analysis_service.py:161-200`).
6. The service re-resolves the authority snapshot, reloads only exact eligible observations, builds the canonical window, atomically persists the immutable window plus exact observation join set, and claims one execution (`telemetry_analysis_service.py:361-507`; `telemetry_repository.py:3458-3815`).
7. `CanonicalAnalysisWindow` revalidates explicit facility scope, V2 Phase 4 identity, canonical signal coverage, one-connection lineage, ordered rows, limits, and the authority digest before the engine call (`backend/app/services/telemetry_analysis_window.py:143-297,385-555`).
8. `run_analysis_window` calls `evaluate_sii` exactly once (`telemetry_analysis_window.py:638-654`). The engine emits the complete analytical modules and currently emits an empty formal `findings` collection (`backend/app/engine/sii_engine.py:1098-1172`).
9. Connector compatibility fields plus the exact SII output feed `build_analysis_result`, which constructs the existing bounded customer-facing result (`telemetry_analysis_window.py:662-690`).
10. `AnalysisWindowExecution` holds the `sii_result`, `analysis_result`, and connector lineage together (`telemetry_analysis_window.py:317-338,691-698`).
11. Completion currently reduces that execution to bounded metadata, IDs, lineage, and a digest before updating `telemetry.analysis_windows` (`telemetry_analysis_service.py:553-576`; `telemetry_lineage.py:289-363`).
12. The scheduler reads only the returned run status (`telemetry_scheduler.py:495-534`). The execution becomes unreachable when the call stack or worker process ends.

## Requested trace findings

### 1. Where the full result first exists

The full engine output first exists as `sii_result` immediately after the one `evaluate_sii` return at `telemetry_analysis_window.py:638-654`. The complete connector result first exists after `build_analysis_result`, as one `AnalysisWindowExecution`, at `telemetry_analysis_window.py:691-698`.

### 2. Where it is discarded

The discard boundary is `run_post_ingestion_analysis`: after SII succeeds, it calls `build_durable_result_lineage`, persists only that reduction, and returns the full execution only to its immediate caller (`telemetry_analysis_service.py:553-576`). `TelemetryScheduler._analyze_final_run` then extracts only `status` (`telemetry_scheduler.py:495-534`). Nothing explicitly deletes the result; there is simply no durable owner or production reload path after the process releases it.

`tests/test_telemetry_full_product_flow.py:934-1052` currently hides this gap by capturing the execution through an in-memory test callback and manually transporting it. Production has no equivalent callback.

### 3. Completion metadata stored today

`telemetry.analysis_windows` stores tenant/workspace/resource/facility scope, system, optional asset, source ingestion run, analysis bounds, status, authority digest, quality summary, execution claim/expiry/attempt count, `completed_at`, `result_digest`, bounded `result_metadata`, and bounded `evidence_lineage`. Exact observation membership is separately normalized in `telemetry.analysis_window_observations` (`backend/db/migrations/create_telemetry_connection_tables.py:523-569`; `extend_telemetry_ingestion_runtime.py:196-213`).

`build_durable_result_lineage` stores observation count and lineage digest, contributing run IDs, bounded finding/evidence IDs plus total/truncation counts, status, and a reference digest. IDs cap at 256; metadata caps at 16 KiB and lineage at 64 KiB. The existing `result_digest` hashes only this reduced metadata/lineage envelope, not the exact `AnalysisWindowExecution` bytes (`telemetry_lineage.py:289-363`).

### 4. How historical/manual-upload evidence reaches product routes

Manual upload finalization first persists an immutable terminal result, verifies it, builds a bounded evidence record, verifies that record, and only then publishes terminal completion (`backend/app/services/upload_jobs.py:633-680,770-776`; `upload_state_repository.py:899-1006,1366-1440`). Exact historical comparison routes validate portfolio/system/baseline/run before loading the linked immutable result (`backend/app/services/baseline_analysis_repository.py:410-469`; `backend/app/routers/data.py:2243-2275`).

The engineering workspace loads scoped `/api/evidence/runs`, converts those bounded records into analysis-shaped models, and overlays finding workflow state from `/api/findings?source_kind=evidence_run&source_run_id=...` (`frontend/src/components/EngineeringReasoningWorkspace.jsx:251-290`; `frontend/src/viewModels/engineeringReasoning.js:800-819`). It routes exact finding IDs through `/findings/{id}`, `/investigations/{id}`, and `/evidence/{id}` (`EngineeringReasoningWorkspace.jsx:35-57,386-400,478-493`).

Each production disclosure depth has an explicit projector and renderer that P0.1 can reuse unchanged:

- Results is projected by `projectResults` (`frontend/src/viewModels/resultsPresentation.js:187-239`) and rendered through `FindingsOverview` -> `OperationsBrief` -> `FindingSummary` (`frontend/src/components/EngineeringReasoningWorkspace.jsx:132-133`; `frontend/src/components/engineering/OperationsBrief.jsx:9-67`; `frontend/src/components/engineering/FindingSummary.jsx:3-36`).
- Finding Review is projected by `projectFindingReview` (`resultsPresentation.js:369-431`) and rendered by `FindingReviewWorkspace` (`frontend/src/components/engineering/FindingCaseWorkspaces.jsx:99-113`).
- Investigation is projected by `projectInvestigation` (`resultsPresentation.js:512-645`) and rendered by `InvestigationWorkspace` (`FindingCaseWorkspaces.jsx:117-135`).
- Evidence Record is projected by `projectEvidenceRecord` (`resultsPresentation.js:646-695`) and rendered by `EvidenceRecordWorkspace` (`FindingCaseWorkspaces.jsx:146-180`).

The existing backend product reads are `GET /api/evidence/runs`, `GET /api/evidence/runs/{run_id}`, `GET /api/findings`, and `GET /api/findings/{finding_id}` (`backend/app/routers/evidence.py:21-34`; `backend/app/routers/findings.py:76-146`). These routes are historical bounded projection/workflow reads, not connector artifact authority; a new connector result must pass exact telemetry scope first and may then feed these existing presentation contracts.

### 5. Reusable persistence/evidence abstractions

Safe patterns to reuse:

- the dedicated PostgreSQL `telemetry` schema, ledgered additive migrations, four-column scope predicate, and readiness verification;
- immutable analysis-window identity and exact normalized observation membership;
- claim-token/status compare-and-swap completion;
- upload terminal-result semantics: hash exact serialized content, insert if absent, verify the existing value on retry, and publish completion only after durable authority exists;
- historical completed-analysis links and rebuildable sidecars;
- the existing bounded `analysis_result`, SII evidence projection, and unchanged progressive-disclosure projectors.

Unsafe as canonical authority:

- `evidence_runs` is scoped SQLite/runtime persistence and is upsertable (`backend/app/services/runtime_db.py:2345-2418`);
- evidence packages are derived governance/presentation objects;
- baseline/shared-state writers use the historical-upload `DatasetScope` family and overwrite keys;
- upload content-addressed storage is tied to upload/S3 infrastructure and would violate the no-AWS boundary;
- the bounded SII projection explicitly is not classification authority (`analysis_result_contract.py:679-754`).

### 6. Existing immutable artifact/blob/evidence pattern

The strongest existing semantic pattern is the manual-upload terminal result bundle: canonical JSON digest, scope/job/attempt validation, insert-if-absent publication, readback digest verification, and divergent-retry rejection (`upload_state_repository.py:899-1006`). The implementation itself is upload-specific and must not own connector data. The connector artifact belongs beside `analysis_windows` in PostgreSQL.

`analysis_window_observations` already owns exact observation membership; a new result artifact should reference that normalized lineage rather than duplicate every observation record.

### 7. Exact retrieval authorization scope

Request security resolves the workspace server-side. Explicit facility workspaces require active membership (or an exact service allowlist), unauthorized selection is an opaque 404, and the middleware installs the authoritative DatasetScope and Phase 4 scope (`backend/app/core/security.py:62-94`; `workspace_authorization.py:83-124`). `current_telemetry_scope()` accepts only that explicit facility context and produces tenant, workspace, deterministic resource scope, and facility identity (`backend/app/services/telemetry_scope.py:34-90`). Repository reads filter all four values together (`telemetry_repository.py:75-83`).

Artifact retrieval must additionally require and compare connection, source run, system, optional asset, window/result identity. `get_analysis_window(scope, window_id)` alone is not sufficient for system isolation within one facility. Artifact ID alone must never authorize access.

Existing evidence/finding APIs filter only the historical `scope_storage_id`; facility/system/asset are response data rather than lookup predicates. They may serve as rebuildable projections after exact connector authorization, but not as the P0.1 retrieval authority.

### 8. Schema-version versus contract-version mismatch

`AnalysisWindowExecution` truthfully exposes `contract_version = analysis-window-execution.v1` (`telemetry_analysis_window.py:317-338`). Canonical `analysis_result` truthfully exposes top-level `schema_version = analysis-result-v1` and nested `analysis_metadata.contract_version = analysis-result-v1` (`analysis_result_contract.py:614-676`). Current durable lineage incorrectly reads `analysis_result.get("contract_version")`, so real connector completion persists an empty `analysis_contract_version` (`telemetry_lineage.py:343-348`).

SII truthfully exposes `engine.name` and `engine.version`; it does not expose a top-level SII schema identifier (`sii_engine.py:1098-1100`). The durable artifact must keep artifact schema, execution contract, analysis schema, analysis metadata contract, and SII engine identity distinct, and must not invent an absent SII schema identity.

When emitted, exact Phase 4 identities are present under `behavioral_model` and `behavioral_snapshots`, including model ID/version, current/previous snapshot ID, and baseline state/version (`backend/app/engine/sii/phase4.py:379-459`). Only supplied values may be indexed.

### 9. Payload-size implications

The audit measured:

| Signals | Exact result bytes | Evidence bytes | Serialization |
|---:|---:|---:|---:|
| 10 | 9.64 MB | 3.12 MB | 0.443 s |
| 50 | 161.41 MB | 51.85 MB | 5.269 s |
| 100 | 161.92 MB | 51.99 MB | 5.520 s |

At 50 signals serialization exceeded engine time by 2.08×. A second full JSONB copy in evidence/product storage would worsen the known copy-heavy plateau. P0.1 therefore needs exactly one authoritative serialized artifact, compressed storage, small indexed metadata, normalized observation references, and a bounded product projection. Oversize persistence must fail completion rather than truncate. P1.2 remains responsible for redesigning internal module duplication.

### 10. Product-required versus diagnostic-only fields

Product/indexed identity:

- full authoritative scope, connection, source run, window, system, optional asset;
- stable artifact/result ID and exact payload digest;
- execution contract, analysis schema/contract, actual engine identity;
- actual model/baseline/snapshot/reference IDs where emitted;
- generated finding/evidence IDs and counts;
- exact observation membership count/digest and authority digest;
- result state, byte counts, serialization/retrieval timing.

Bounded product projection:

- the existing exact `analysis_result` and its bounded `sii_evidence`;
- top-level artifact/window/reference identity needed by the view model;
- empty finding collections preserved for stable and insufficient results.

Artifact-only diagnostic/audit content:

- complete `sii_result`, processing trace, temporal/covariance/multiscale/physics/Phase 4 modules, uncertainty, storage traces, and the complete execution envelope.

Excluded from the artifact:

- claim tokens, credentials, secret references, provider configuration, raw provider payloads, and duplicated observation rows. Exact canonical values remain owned by normalized observations and their immutable membership links.

## Current restart and failure behavior

- Repeating a completed window returns `reused_existing=True`, calls SII zero times, but returns `execution=None`; only reduced metadata survives (`telemetry_analysis_service.py:212-223,361-364`).
- A stale running claim becomes terminal failed and is never automatically rerun (`telemetry_repository.py:3817-3856`).
- If SII succeeds but completion persistence fails, the in-memory result is lost and the scheduler reports analysis failure while ingestion may still complete.
- If completion commits and the process dies before returning, a retry recognizes `completed` but cannot retrieve the original result.

P0.1 must make exact artifact durability a prerequisite of completed status, make identical retry idempotent, reject divergent content for the same identity, and load the exact artifact after restart without invoking SII.

## Trace conclusion

The defect is exactly bounded: the authoritative connector handoff reaches a complete `AnalysisWindowExecution`, but completion has no immutable artifact owner and the scheduler discards the only live reference. Existing product projectors already implement the required hierarchy and should remain unchanged. P0.1 should add one scoped immutable PostgreSQL artifact, derive bounded product transport from it, and keep historical evidence/workflow rows as rebuildable projections rather than authority.
