# P0.1 Canonical Connector Result Review Package

Date: 2026-08-26
Scope: P0.1 only
Worktree: `/home/ubuntu/Neraium-1.0-canonical-result`
Branch: `agent/canonical-connector-result`

## Closure summary

A completed production connector window now publishes one compressed, immutable `AnalysisWindowExecution` artifact to `telemetry.analysis_result_artifacts`. The artifact and the analysis-window transition to `completed` are committed in one database transaction. Authorized reads verify the exact artifact bytes, digest, schema/contract identities, complete normalized-observation membership, and full tenant/workspace/facility/connection/run/system/asset/result scope before deriving a bounded product projection. Retrieval never imports or invokes SII.

The exact durable response is routed through the existing hierarchy:

1. Results uses the existing triage projection and original finding IDs.
2. Finding Review uses the exact selected finding when one exists.
3. Investigation uses the same result/finding identity and bounded technical channels with explicit source/truncation qualification.
4. Evidence Record uses the same result/finding identity, exact IDs/versions/digests/reference metadata, and one bounded verified observation-lineage read.

Stable/no-material-change and zero-finding insufficient results remain retrievable. They use the canonical result ID for Investigation/Evidence and do not create fake findings. Finding Review remains unavailable when no real finding exists.

## Previous discard and new authority

The full result first exists after `evaluate_sii` and `build_analysis_result` return together as `AnalysisWindowExecution` in `backend/app/services/telemetry_analysis_window.py:638-698`. Before P0.1, `run_post_ingestion_analysis` persisted only bounded metadata/IDs/lineage/a reduced digest and returned the execution in process; the scheduler reduced that return to status, so the only full artifact vanished with the call stack or worker process.

P0.1 inserts `build_canonical_result_artifact(execution)` immediately after successful analysis and supplies it to `finish_analysis_window_execution` (`backend/app/services/telemetry_analysis_service.py:572-640`). `backend/app/services/telemetry_repository.py` owns the atomic immutable publication.

## Storage and immutable identity

Migration `005_persist_canonical_analysis_results` adds `telemetry.analysis_result_artifacts`:

- primary UUID result ID;
- tenant, workspace, resource scope, facility, connection, source run, analysis window, system, nullable asset, and window bounds;
- authority digest and exact observation count/lineage digest;
- artifact schema, execution contract, analysis schema, analysis contract, and actual optional engine/reference identities;
- bounded finding/evidence ID envelopes;
- canonical payload encoding/digest/byte counts/timing and compressed `BYTEA` payload.

The result ID is deterministic UUIDv5 over the deterministic window ID and execution contract. The payload digest is SHA-256 over sorted compact canonical UTF-8 JSON before compression. Identical retry reuses the same ID/digest; different bytes for the same exact window conflict rather than overwrite. A database trigger rejects UPDATE and DELETE, full scoped foreign keys use `ON DELETE RESTRICT`, and an insert trigger checks the window/run/connection/system/asset/bounds/authority identity.

The exact execution artifact is stored once. Observation rows are not copied into it; the durable `analysis_window_observations` membership is referenced and proven by count/digest. Product projections are rebuilt transiently and are not durably duplicated. Artifact construction, decode, and repository publication independently bind the payload to the exact analysis window, source run, and deterministic result ID; a cross-window artifact is rejected before SQL.

## Completion, restart, and recovery

- SII success plus artifact-write failure: the window is transitioned to failed with `telemetry_analysis_result_persistence_failed`; it does not claim retrievable completion.
- Artifact publication and completed status are one transaction, so a process cannot durably commit only one of them.
- A process death after transaction commit is recovered through the completed window's canonical result ID/digest; retry calls SII zero times.
- Identical repeated completion is idempotent; divergent artifacts for the same scoped window raise a conflict.
- Projection failure leaves the immutable artifact unchanged and emits a bounded failure event; a later read can rebuild the projection without SII.
- Legacy completed windows without an artifact remain historical status records but are not reconstructed or rerun.

## Authorization and retrieval

The existing request middleware resolves tenant/workspace/facility membership and installs `TelemetryScopeRef`. The connector routes first require the connection under that scope. Exact artifact reads additionally require connection ID, source run ID, system ID, null-safe asset ID, and result ID. Repository queries repeat resource, tenant, workspace, and facility predicates and join only completed windows whose stored result digest equals the artifact digest.

Routes remain in the existing Data Connections API family:

- `GET /api/data-connections/{connection}/runs/{run}/analysis-results`
- `GET /api/data-connections/{connection}/runs/{run}/systems/{system}/analysis-results/{result}?asset_id=...`
- `GET .../{result}/lineage?asset_id=...&limit=...&cursor=...`

There is no artifact-ID-only or unscoped latest-result route. Mismatched scope/identity returns the same opaque 404 as absence. Result detail reads decode and checksum the artifact, compare every indexed version/identity, reload all lineage joins, recompute the count/digest, and validate record connection/system/asset/authority before projection. The Evidence lineage route loads only scoped immutable artifact metadata plus the linked membership, recomputes the same count/digest/scope proof, and returns up to the complete 5,000-member bound in one product request without decompressing the analytical artifact again.

## Schema and contract identity fix

The implementation records these distinct values without inventing an SII schema:

- artifact schema: `telemetry-canonical-result-artifact.v1`;
- execution contract: actual `AnalysisWindowExecution.contract_version`;
- analysis schema: actual `analysis_result.schema_version`;
- analysis contract: actual `analysis_result.analysis_metadata.contract_version`;
- SII engine name/version only when emitted;
- model/baseline/snapshot references only at emitted source paths.

The former durable-lineage read of nonexistent `analysis_result.contract_version` was replaced with the real top-level schema plus the nested contract.

## Projection and payload discipline

The immutable payload cap is 256 MiB uncompressed. Projection caps are 1 MiB shared envelope, 256 KiB per technical channel, 2 MiB combined technical channels, and 256 KiB audit metadata. Normalized telemetry `records` are excluded from both top-level and nested data-quality projections. Truncated or withheld technical channels retain source path, original/selected byte and item counts, canonical result/digest reference, and visible UI qualification.

Measured with the authoritative connector restart fixture (3 mapped signals, 360 observations):

| Item | Measurement |
|---|---:|
| Canonical artifact, uncompressed | 2,012,524 B (1.919 MiB) |
| Stored zlib artifact | 109,183 B (0.104 MiB) |
| Compression ratio / reduction | 5.4252% / 94.575% |
| Logical indexed metadata | 3,806 B across 30 fields |
| Product projection | 877,048 B (0.836 MiB) |
| Shared / technical / audit | 113,389 / 729,326 / 11,772 B |
| Artifact serialization/hash/compression | 245.730 ms |
| Projection serialization | 565.500 ms |
| First restart retrieval | 805.824 ms reported; 808.783 ms wall |
| Warm retrieval (20) | 918.550 ms median; 980.166 ms p95 |

These timings use the in-memory acceptance repository and exclude PostgreSQL/network latency. The logical index is compact JSON, not PostgreSQL physical row size.

The earlier four-page lineage measurement was superseded by the final bounded transport: Evidence now requests the exact observation count once (maximum 5,000), and the backend performs one metadata-only full membership verification without another artifact decode. That final lineage path was functionally verified at 360 observations and browser-verified with the canonical connector route; a new comparable latency measurement was not taken after this safety correction.

The audit's different 50-signal workload measured 161,410,689 B result, 51,854,562 B evidence, and 5.268675 s serialization. No apples-to-apples reduction is claimed. P0.1 does not add durable per-surface module copies, but it faithfully retains the existing copy-heavy result and therefore does not solve P1.2.

## Observability

Bounded structured events cover artifact persisted, artifact already exists, persistence failure, authorized retrieval, authorization rejection, schema/version mismatch, integrity failure, and projection failure. Events include bounded IDs/digests/byte counts/timings/error codes only; they do not log raw telemetry, full evidence payloads, credentials, or secrets.

## Verification ledger

- Phase 4 independent retry review: PASS, 67 focused assertions.
- Backend final gate: 256 collected, 254 passed, 2 skipped, 131.02 s. Skips are only the explicit PostgreSQL migration/contract tests because `NERAIUM_TEST_POSTGRES_DSN` is unset.
- Backend compileall: PASS.
- Frontend `npm run verify`: PASS; lint, build, performance budgets, 60 files / 501 tests.
- Chromium setup: `npm run setup:codex` PASS with locked dependencies.
- Relevant existing Chromium suites: 7/7 PASS.
- New exact canonical connector Chromium path: 1/1 PASS; full Data Connections Chromium spec 3/3 PASS.
- The new browser path asserts exact list/detail/lineage GET order, all four product depths, same finding/result/digest/lineage identities, and zero SII/analysis/retry/backfill mutations.
- `git diff --check`: PASS.

No migration was applied. Live PostgreSQL trigger/FK execution remains unverified locally because no test DSN was configured; the DDL contract/idempotency/readiness tests pass.

## Migration deployment and rollback

Required ordering is: apply migration 005 through the controlled process in a non-production environment; verify ledger/columns/indexes/FKs/triggers; deploy code that requires readiness for 005; observe bounded result events before any broader rollout. Application rollback is safe because the additive immutable table may remain unused. Database downgrade intentionally refuses to drop the canonical authority. Existing historical/manual paths remain in place.

## Explicit remaining P0.2+ work

Not implemented:

- P0.2 event-time authority for backfill/live learning;
- P0.3 single cross-product finding/reference authority;
- P0.4 insufficiency semantic changes;
- P0.5 suppression/persistence qualification changes;
- P0.6 upload facade removal;
- P1.1 cross-connection system windows/relevance routing;
- P1.2 the internal 161 MB evidence/module-copy redesign;
- covariance, Phase 4 storage, temporal preprocessing, live-route, or analytical-method changes.

No Health Relevance code was added. No SII math, threshold, classification, suppression, or persistence-qualification behavior was changed.

## Repository state

- Branch: `agent/canonical-connector-result`.
- Local HEAD: `519be2c59f22b52fb4affe33297fffc942be09ef`.
- Work remains modified/untracked and uncommitted for review.
- `origin/main` advanced by two Health Relevance commits during this campaign; this branch was deliberately not updated because Health Relevance is explicitly out of scope and no automatic merge was authorized.
- No commit, push, PR, merge, deployment, AWS change, or production migration was performed.

## Final independent review

- Product hierarchy/scope: PASS after adding synchronous authority switching so a manual/historical result cannot remain shadowed by a prior connector selection.
- Security/privacy/performance: PASS after routing the full valid system-ID contract, binding window/run/result before insert, and replacing repeated full-artifact lineage paging with one bounded metadata-only membership verification.
- Correctness/durability: PASS after the reviewer's cross-window persistence finding was fixed with pre-SQL window/run/result binding and a passing regression.

Non-blocking residuals: the optional live-PostgreSQL DDL/trigger tests were not run; the restart fixture recreates services/runtime over a durable-repository test double rather than launching a separate PostgreSQL-backed process; the existing ~161 MB payload still incurs one large decode/projection and remains P1.2; a worst-case 5,000-record lineage response/DOM has not been production-profiled; and lineage-link immutability is enforced by application write convention while every retrieval rehashes and fails closed on mutation.
