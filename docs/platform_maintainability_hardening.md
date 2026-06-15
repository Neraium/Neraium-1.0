# Platform Maintainability Hardening

## Current Architecture

The upload pipeline remains externally compatible through `backend/app/services/upload_jobs.py`, but responsibility is now split into focused helpers and explicit state ownership services:

- `upload_state.py`: canonical upload identity and latest-upload record contract
- `upload_validator.py`: CSV sniffing, shape detection, cleaning-safe snapshot extraction
- `upload_replay.py`: replay identity and replay frame construction helpers
- `upload_parser.py`: JSON-to-CSV normalization for upload ingestion
- `upload_completion.py`: partial-completion artifact assembly
- `upload_evidence.py`: upload traceability packet and evidence-record assembly
- `upload_persistence.py`: summary generation and upload history reads
- `upload_runtime_state.py`: explicit in-process ownership for jobs, latest-upload cache, reset-block state, and upload-state client reuse
- `upload_state_repository.py`: backend repository for latest-upload records, summary/result artifacts, and shared-state reads/writes
- `upload_queue_lifecycle.py`: queue dispatch lifecycle separated from the compatibility facade

`upload_jobs.py` is now the compatibility facade that keeps public imports stable while delegating state ownership, queue lifecycle handling, and persisted upload-state access. This pass reduced its role further by moving read-only callers onto focused modules and moving completion write sequencing into the repository layer.

## Upload State Flow

1. `/api/data/upload` creates a queued upload job and writes initial status.
2. `upload_jobs.process_next_queued_upload_job()` claims the job and delegates parsing/cleaning.
3. `upload_validator.stream_csv_snapshot()` produces the cleaned telemetry snapshot used for analysis.
4. `upload_jobs` builds the analysis result, then `upload_state_repository.write_upload_completion()` owns the persisted result/summary/latest-upload write sequence.
5. `upload_queue_lifecycle.py` owns queue dispatch transitions while using the explicit `UploadRuntimeState` instance.
6. `latest-upload`, replay, facility, evidence, and frontend session restoration resolve the active upload from the canonical `current_upload` contract.

## Module Ownership

- `upload_jobs.py`
  Orchestration, queue lifecycle, SII runner invocation, compatibility exports.
- `upload_state.py`
  Upload identity normalization, canonical latest-upload record assembly, session-scope rules.
- `upload_validator.py`
  Delimiter/header detection, row filtering, timestamp and numeric cleaning decisions.
- `upload_replay.py`
  Replay timeline derivation and replay-oriented numeric helpers.
- `upload_parser.py`
  Normalization of JSON payload uploads into CSV-shaped processing input.
- `upload_completion.py`
  Safe partial-result packaging when analysis cannot fully complete.
- `upload_evidence.py`
  Traceability packet construction plus upload evidence-record assembly.
- `upload_persistence.py`
  Upload summaries and history reads used by observability/latest-upload views.
- `upload_runtime_state.py`
  Explicit ownership of in-process upload state that previously lived in `upload_jobs.py` globals.
- `upload_state_repository.py`
  Upload-state persistence contract for local files, runtime DB latest payloads, and shared S3 state.
- `upload_queue_lifecycle.py`
  Queue lifecycle transitions for claim/process/fail/complete behavior.

## Cache Ownership

Removed in this phase:

- Route-level `_UPLOAD_STATUS_CACHE` in `backend/app/routers/data.py`
- Route-level `_LATEST_UPLOAD_CACHE` in `backend/app/routers/data.py`
- `upload_jobs.py` globals for jobs/latest-upload cache/reset-block state

Current cache/state owners:

- `backend/app/services/upload_runtime_state.py`
  `UPLOAD_RUNTIME_STATE.jobs`, `UPLOAD_RUNTIME_STATE.latest_upload_cache`, `UPLOAD_RUNTIME_STATE.reset_block_persisted`, `UPLOAD_RUNTIME_STATE.upload_state_s3_client`
  Reason: one explicit service object now owns upload runtime state and shared client reuse for latest-upload persistence.
- `backend/app/services/runtime_db.py`
  `_S3_CLIENT`
  Reason: queue backend client reuse still remains process-global in the runtime DB module.
- `frontend/src/services/api/uploadApi.js`
  short-lived latest-upload fetch dedupe cache
  Reason: explicit client-side request coalescing.

Policy:

- Canonical active-upload identity must come from `current_upload` / `read_latest_upload_record()` before any compatibility fallback field.
- Non-job-scoped latest-upload reads should go through `upload_state_repository.py`, not raw file/shared-state access.
- Job-scoped artifact reads are allowed only through explicit per-job helpers such as `read_upload_result_by_job_id()`.
- Reset flows must clear persisted latest-upload state and leave no route-level cache residue.

See also: [cache_ownership_policy.md](cache_ownership_policy.md)

## Remaining Technical Debt

- `upload_jobs.py` still owns orchestration plus compatibility exports for queue/reset/build flows even though state ownership and completion sequencing moved out.
- `backend/app/services/runtime_db.py` still owns a process-global `_S3_CLIENT` for queue storage.
- Some backend and frontend contracts still preserve `latest_result` for compatibility, even where `current_upload.result` is now preferred.
- Evidence and replay enrichment still happen across routers and service boundaries instead of one upload-state resolver.

## This Pass

Migrated out of `upload_jobs.py`:

- `read_current_upload_result` callers in `facility.py`, `audit.py`, `domain_mode.py`, `backend/api/ecosystem.py`, `backend/api/distributed_cognition.py`, and `data_connections.py` now import from `upload_state_repository.py`.
- `shared_state_configured`, `upload_state_backend`, and `warm_latest_upload_cache` callers in app startup and health paths now import from `upload_state_repository.py`.
- `has_active_session_artifact` in `facility.py` now imports from `upload_state.py`.
- `replay.py` now reads replay payloads directly from `upload_state_repository.py`.
- `data.py` now reads canonical latest-upload state from `upload_state_repository.py` and uses `upload_evidence.py` for upload evidence enrichment.
- `data_connections.py` now imports `summarize_result` from `upload_persistence.py` and latest-upload write helpers from `upload_state_repository.py`.
- `observability.py` now reads upload history from `upload_persistence.py` using `UPLOAD_RUNTIME_STATE.runtime_dir` plus canonical `read_current_upload_result()`.

Remaining compatibility exports in `upload_jobs.py`:

- `configure_runtime_dir`
  Reason: startup/app test bootstrapping still expects the facade entrypoint.
- `process_next_queued_upload_job`, `process_csv_file`, `process_json_payload`, `process_csv_content`, `build_upload_result`
  Reason: these are orchestration/processing entrypoints, not pure state helpers.
- `write_job`, `read_job`, `read_upload_status`, `reset_latest_upload_state`
  Reason: queue lifecycle and reset callers still depend on the facade surface.
- `write_latest_upload_result`, `write_latest_upload_summary`, `read_latest_upload_record`, `read_upload_result_by_job_id`
  Reason: preserved for compatibility while tests and callers continue migrating off legacy imports.
- `build_evidence_record_from_result`, `build_traceability_packet`, `read_upload_cache_stats`
  Reason: compatibility exports remain for older internal callers, even though canonical callers now use `upload_evidence.py` and `upload_state_repository.py` directly.

Completion write sequencing:

- `upload_state_repository.write_upload_completion()` now owns the persisted write ordering for per-job result, per-job status, latest result, latest summary, and canonical latest-upload record.
- `upload_jobs.py` no longer hand-orders those writes separately for normal completion and partial completion paths.

`latest_result` migration status:

- Canonical resolution prefers `current_upload.result` wherever canonical latest-upload state is available.
- Frontend normalization still falls back to `latest_result` and `latestResult` for backward-compatible payloads.
- Backend `latest-upload` style responses still expose `latest_result` where required for compatibility, but active-upload reads now route through canonical record helpers first.

Benchmark status:

- The 1M-row benchmark remains opt-in by design.
- Run it only when explicitly desired with `NERAIUM_RUN_1M_BENCHMARK=1`.
- Smaller-scale benchmark validation remains acceptable for routine hardening passes.

## Future Refactor Opportunities

1. Migrate the remaining `write_latest_upload_result` and `write_latest_upload_summary` compatibility imports in tests and services onto `upload_state_repository.py`.
2. Remove compatibility re-exports for `build_evidence_record_from_result` and `build_traceability_packet` once no internal callers still import them from `upload_jobs.py`.
3. Remove legacy `latest_result` contract fields only after all downstream callers and persisted-response tests are fully migrated.
4. Convert `runtime_db.py` queue/shared-state clients to explicit ownership/injection.
5. Consolidate replay/evidence/latest-upload resolution behind one backend current-upload helper layer.
