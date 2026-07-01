# CSV Upload 503 Root Cause

Date: 2026-06-30

## Failing Request

Production returned raw HTML 503 from the edge before the FastAPI app handled the request. The same HTML response was confirmed on:

- `GET https://app.neraium.com/api/health`
- `GET https://app.neraium.com/api/data/latest-upload?include_persisted=1`
- `GET https://app.neraium.com/api/routes/debug`

For the CSV flow this means `POST /api/data/upload` and subsequent upload polling/result routes could also return the same HTML 503 while the API target group had no healthy targets.

Response markers:

- `server: awselb/2.0`
- `x-cache: Error from cloudfront`
- `content-type: text/html`
- body title `503 Service Temporarily Unavailable`

## Why It Happened

The ECS API service had desired count 1 and running count 0 because the ALB health check to port 80 timed out. Recent upload/replay/result-flow changes made `/api/health` perform upload-session diagnostics. That path resolved latest upload/session state and queue metrics, so a load-balancer health check depended on upload state and runtime diagnostics instead of a lightweight app liveness check. When health timed out, ECS drained the only API task, so CloudFront/ALB returned raw HTML 503 before FastAPI could return JSON.

A second reliability issue was that production API tasks could still dispatch a local upload worker thread after accepting an upload. In split-role production, the API and worker services share S3-backed upload state and the worker service should claim the queued job. Running analysis from the API task can starve request handling and health checks during CSV processing.

## Fix

- `/api/health` no longer resolves upload-session state. It returns lightweight JSON for ALB liveness.
- Verbose upload/session diagnostics remain available on `/api/ready?verbose=true`.
- `POST /api/data/upload` still accepts CSV/JSON/TXT and returns a JSON `job_id`.
- In production API split-role mode with shared upload state configured, uploads are persisted and queued with `worker_dispatch_status=external_worker_queue`; the API does not start a local analysis worker thread.
- Local/development uploads still dispatch a local thread so targeted tests and single-process deployments continue to complete.
- Upload request and queue lifecycle logs now include request id, endpoint, file name, file size, job id, queue/dispatch status, processing stage, elapsed time, failure reason, and server-side stack traces on exceptions.

## Verification

Run targeted checks only:

```bash
python -m py_compile backend/app/routers/data.py backend/app/routers/health.py backend/app/services/service_status.py backend/app/services/upload_queue_lifecycle.py
./.venv/bin/pytest -q tests/test_health.py tests/test_data_upload.py::test_upload_returns_accepted_job_id tests/test_data_upload.py::test_upload_in_split_role_production_uses_external_worker_queue tests/test_data_upload.py::test_upload_error_payload_sanitizes_html_service_unavailable tests/test_data_upload.py::test_upload_rejects_saturated_queue tests/test_analysis_result_contract.py::test_analysis_completion_does_not_require_replay tests/test_analysis_result_contract.py::test_saved_analysis_result_is_viewable_without_replay
cd frontend && npm test -- --run src/viewModels/__tests__/uploadFlow.test.js src/services/api/uploadApi.test.js src/components/DataConnectionsWorkspace.stale-progress.test.js
```

After deployment, verify production:

```bash
curl -i https://app.neraium.com/api/health
```

Expected: HTTP JSON response from FastAPI, not ALB/CloudFront HTML. Then upload a small CSV and the wastewater lift station CSV, confirm `POST /api/data/upload` returns JSON with `job_id`, `GET /api/data/upload-status/{job_id}` reaches `COMPLETE`, and the results page opens without replay being required.
