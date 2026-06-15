# Platform Maintainability Hardening

## Current Architecture

The upload pipeline remains externally compatible through `backend/app/services/upload_jobs.py`, but responsibility is now split into focused helpers:

- `upload_state.py`: canonical upload identity and latest-upload record contract
- `upload_validator.py`: CSV sniffing, shape detection, cleaning-safe snapshot extraction
- `upload_replay.py`: replay identity and replay frame construction helpers
- `upload_parser.py`: JSON-to-CSV normalization for upload ingestion
- `upload_completion.py`: partial-completion artifact assembly
- `upload_persistence.py`: summary generation and upload history reads

`upload_jobs.py` is the compatibility facade that keeps public imports stable while orchestrating queueing, SII execution, and persistence.

## Upload State Flow

1. `/api/data/upload` creates a queued upload job and writes initial status.
2. `upload_jobs.process_next_queued_upload_job()` claims the job and delegates parsing/cleaning.
3. `upload_validator.stream_csv_snapshot()` produces the cleaned telemetry snapshot used for analysis.
4. `upload_jobs` builds the analysis result and writes canonical latest-upload state through `upload_state.py`.
5. `latest-upload`, replay, facility, and frontend session restoration resolve the active upload from the canonical `current_upload` contract.

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

## Cache Inventory

Removed in this phase:

- Route-level `_UPLOAD_STATUS_CACHE` in `backend/app/routers/data.py`
- Route-level `_LATEST_UPLOAD_CACHE` in `backend/app/routers/data.py`

Remaining cache/state surfaces:

- `backend/app/services/upload_jobs.py`
  `JOBS`, `LATEST_UPLOAD_CACHE`, `_S3_CLIENT`, `_RESET_BLOCK_PERSISTED`
  Reason: compatibility with existing queue/status interfaces and shared-state backends.
- `backend/app/services/runtime_db.py`
  `_S3_CLIENT`
  Reason: backend client reuse for shared queue/state storage.
- `frontend/src/services/api/uploadApi.js`
  short-lived latest-upload fetch dedupe cache
  Reason: explicit client-side request coalescing.

## Remaining Technical Debt

- `upload_jobs.py` still owns orchestration plus several write paths and should eventually move to an explicit service object.
- Shared-state backend access is still process-global rather than dependency-injected.
- Evidence and replay enrichment still happen across routers and service boundaries instead of one upload-state resolver.
- Frontend still carries both `latest_result` and `current_upload` compatibility paths.

## Future Refactor Opportunities

1. Replace `upload_jobs.py` globals with an explicit upload runtime/state service instance.
2. Move evidence-run enrichment into a dedicated upload state resolver service.
3. Unify per-job status/result reads behind a single backend contract object.
4. Remove compatibility aliases once all callers read `current_upload.result`.
5. Convert shared-state and queue storage clients to explicit ownership/injection.
