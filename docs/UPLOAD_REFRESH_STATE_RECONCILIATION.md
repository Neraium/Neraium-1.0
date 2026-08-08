# Upload refresh state reconciliation

## Root cause

The upload UI had three independent sources of “activity” and treated each as if it were backend job truth:

1. Workspace hydration copied a queued/processing snapshot into `running_sii` before checking the job-specific status endpoint.
2. The in-process worker wrote `worker_state=running` before `claim_next_upload_job()` atomically changed the queue row from `pending` to `processing`.
3. Status enrichment preserved that pre-claim worker string, and the frontend rendered `Analysis active` from it even when the canonical backend state was still queued.

That explains the production contradiction (`processing_state=queued` with `worker=Analysis active`). After refresh the browser file input correctly became empty, but the component reused that empty input label as the processing dataset label and locked all file-selection paths from its cached `running_sii` state. A missing status response was retried as synthetic `PROCESSING`, and transient status failures also replaced the last valid backend state with synthetic processing. Those behaviors could leave the page attached to a phantom job indefinitely.

## Architecture and concurrency

The backend supports multiple durable job IDs and multiple pending queue entries. A worker may process them serially, but accepting another upload does not require cancelling or destroying an existing job. The frontend therefore permits the operator to detach from the displayed job and start another upload. Detaching only changes browser presentation; the backend job and its dataset/job identifiers remain intact and can be viewed again.

Cancellation is not exposed because the upload API does not implement a cancellation operation.

## Authoritative reconciliation rules

- A remembered job ID is only allowed to lock/show the processing UI after `GET /api/data/upload-status/{job_id}` succeeds in the current authenticated dataset scope.
- `404 NOT_FOUND` clears the obsolete browser reference and returns the upload controls to idle; it never changes a backend job.
- Completed and failed jobs stop polling. Their recovery/open/retry actions remain available.
- A pending queue row is `queued`, even if an earlier process heartbeat says running.
- A queue row becomes `claimed` only when its durable claim fields (`status=processing` plus lock/attempt evidence) exist.
- A claimed job becomes `processing` when backend processing stages advance.
- A worker refreshes the claimed queue row every 30 seconds while processing. A claimed job with no fresh job-specific heartbeat for 180 seconds is `stalled`.
- A legacy processing job without a queue row may be shown as processing only while its backend update evidence is fresh; otherwise it is `stalled`.
- Polling activity is never evidence of worker activity.
- Transient poll errors preserve the last valid backend payload. Exhausted retries become `waiting` with a resume action, not a fabricated job failure.
- The native file input is ephemeral and is never persisted. Processing cards use the backend filename/dataset identity and never describe the refreshed empty picker as the processing source.
- Browser job references are versioned and scoped by user plus workspace. A legacy unscoped key is accepted only as a candidate and is migrated after backend scope validation.
