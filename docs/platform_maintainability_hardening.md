# Platform Maintainability Hardening

## Current Architecture

The upload pipeline remains externally compatible through `backend/app/services/upload_jobs.py`, but responsibility is now split into focused helpers and explicit state ownership services:

- `upload_state.py`: canonical upload identity and latest-upload record contract
- `upload_validator.py`: CSV sniffing, shape detection, cleaning-safe snapshot extraction
- `upload_replay.py`: replay identity and replay frame construction helpers
- `upload_parser.py`: JSON-to-CSV normalization for upload ingestion
- `upload_completion.py`: partial-completion artifact assembly
- `upload_persistence.py`: summary generation and upload history reads
- `upload_runtime_state.py`: explicit in-process ownership for jobs, latest-upload cache, reset-block state, and upload-state client reuse
- `upload_state_repository.py`: backend repository for latest-upload records, summary/result artifacts, and shared-state reads/writes
- `upload_queue_lifecycle.py`: queue dispatch lifecycle separated from the compatibility facade

`upload_jobs.py` is now the compatibility facade that keeps public imports stable while delegating state ownership, queue lifecycle handling, and persisted upload-state access.

## Upload State Flow

1. `/api/data/upload` creates a queued upload job and writes initial status.
2. `upload_jobs.process_next_queued_upload_job()` claims the job and delegates parsing/cleaning.
3. `upload_validator.stream_csv_snapshot()` produces the cleaned telemetry snapshot used for analysis.
4. `upload_jobs` builds the analysis result and writes canonical latest-upload state through `upload_state.py` plus `upload_state_repository.py`.
5. `upload_queue_lifecycle.py` owns queue dispatch transitions while using the explicit `UploadRuntimeState` instance.
6. `latest-upload`, replay, facility, and frontend session restoration resolve the active upload from the canonical `current_upload` contract.

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

- `upload_jobs.py` still owns orchestration plus compatibility write paths even though state ownership moved out.
- `backend/app/services/runtime_db.py` still owns a process-global `_S3_CLIENT` for queue storage.
- Evidence and replay enrichment still happen across routers and service boundaries instead of one upload-state resolver.
- Frontend still carries both `latest_result` and `current_upload` compatibility paths.

## Future Refactor Opportunities

1. Finish moving the remaining compatibility writes out of `upload_jobs.py` and into repository/service helpers.
2. Move evidence-run enrichment into a dedicated upload state resolver service.
3. Remove compatibility aliases once all callers read `current_upload.result`.
4. Convert `runtime_db.py` queue/shared-state clients to explicit ownership/injection.
5. Consolidate replay/evidence/latest-upload resolution behind one backend current-upload helper layer.
