# Cache Ownership Policy

## Canonical Rules

- The canonical active upload is `current_upload` from `latest_upload.json` / shared-state `latest_upload`.
- `latest_result` remains a compatibility field only. Callers must prefer `current_upload.result` when it exists.
- Non-job-scoped reads must go through `backend/app/services/upload_state_repository.py`.
- Job-scoped reads must use explicit helpers such as `read_upload_result_by_job_id()` and `read_upload_status()`.

## Backend Owners

- `upload_runtime_state.py` owns in-process jobs, latest-upload cache, reset-block state, and upload-state S3 client reuse.
- `upload_state_repository.py` owns latest-upload persistence for local files, runtime DB latest payloads, and shared S3 objects.
- `runtime_db.py` still owns queue persistence plus a remaining process-global `_S3_CLIENT`.

## Reset Expectations

- Reset must clear canonical latest-upload state, compatibility latest payloads, and in-process upload runtime state.
- Routes must not keep independent upload caches after reset.
- Tests should verify that repeated `/api/data/latest-upload` reads stay empty after reset until a new upload becomes current.

## Remaining Exceptions

- `runtime_db.py::_S3_CLIENT` remains global until queue storage gets the same explicit ownership treatment.
- Frontend fetch dedupe in `frontend/src/services/api/uploadApi.js` remains allowed because it is bounded, request-scoped, and not a source of canonical upload identity.
