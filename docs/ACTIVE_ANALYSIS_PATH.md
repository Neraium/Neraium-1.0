# Active Analysis Path

This note records the active Neraium SII path after the legacy cleanup. The current product flow is:

1. Telemetry enters through `POST /api/data/upload` in `backend/app/routers/data.py`, or through the data connection poller in `backend/app/services/data_connections.py`.
2. Uploads are recorded as queued evidence runs and queue jobs through `backend/app/services/runtime_db.py`, `backend/app/services/upload_jobs.py`, and `backend/app/services/evidence_store.py`.
3. Upload processing runs through `backend/app/services/upload_jobs.py` into `backend/app/services/upload_pipeline.py`.
4. `upload_pipeline.py` builds data quality, baseline, relationship, driver attribution, operator report, and upload intelligence outputs, then runs `backend/app/services/sii_runner.py`.
5. `sii_runner.py` uses `BackendSiiRunner` and persists `latest_sii_state` through runtime DB/latest-payload storage.
6. Upload completion writes canonical result, summary, latest-upload state, replay, and evidence through `backend/app/services/upload_state_repository.py` and `backend/app/services/upload_evidence.py`.
7. `GET /api/data/latest-upload` resolves the canonical latest upload through `backend/app/services/latest_upload_state.py`.
8. `GET /api/facility/systems` returns systems only when a valid active upload/result exists. Before analysis it returns empty systems and empty intelligence status.
9. Frontend runtime state in `frontend/src/hooks/useFacilityRuntime.js` consumes latest-upload and facility-system APIs. It now starts with no fallback systems and only displays systems returned by the backend.

## Active Modules

The active upload/analyze/dashboard path depends on these backend areas:

- `backend/app/routers/data.py`
- `backend/app/routers/facility.py`
- `backend/app/routers/evidence.py`
- `backend/app/services/upload_jobs.py`
- `backend/app/services/upload_pipeline.py`
- `backend/app/services/sii_runner.py`
- `backend/app/services/sii_intelligence.py`
- `backend/app/services/structural_cognition.py`
- `backend/app/engine/*`
- `backend/app/services/upload_state_repository.py`
- `backend/app/services/latest_upload_state.py`
- `backend/app/services/system_interpretation.py`
- `backend/app/services/evidence_store.py`

The active frontend consumption path is:

- `frontend/src/hooks/useFacilityRuntime.js`
- `frontend/src/services/api/uploadApi.js`
- `frontend/src/services/api/systemApi.js`
- `frontend/src/components/workspaces/SystemBody/SystemBodyWorkspace.jsx`
- `frontend/src/components/OperationalWorkflowWorkspace.jsx`

## Dependency Audit Result

Confirmed-dead files removed in this cleanup had no active app imports, no API-route dependency, no frontend dependency, and no current test dependency. The removed set was:

- `backend/demo/*`
- `backend/embedded/*`
- `backend/neraium_core/*`
- `backend/run_local_monolith.py`
- `backend/interoperability/sii_event_schema.py`
- `backend/interoperability/sii_import_adapters.py`
- `legacy/upload-replay-v1/*`
- `backend/safety/read_only_guard.py` (abandoned utility; no imports or runtime boundary calls)

Verification checks used before removal:

- Direct module/file-name search across backend, frontend, tests, scripts, docs, and CI files.
- Mounted route review from `backend/app/main.py`.
- Active upload execution path review from `backend/app/routers/data.py`, `backend/app/services/upload_jobs.py`, `backend/app/services/upload_pipeline.py`, and `backend/app/services/sii_runner.py`.
- Top-level backend package import scan confirming other SII-adjacent packages remain reachable through mounted routes, `structural_cognition`, or current tests.

The current replay route keeps explicit `mode=demo` and `mode=aquatic_demo` synthetic responses inside `backend/app/routers/replay.py` for compatibility tests, but production live replay does not fall back to these synthetic payloads.

## Do Not Reintroduce

Do not reintroduce a second SII engine, FD004 validation runner, monolith runner, embedded cognition shim, demo replay package, or legacy upload/replay router into the production import path. New analysis work should extend the active upload pipeline and `BackendSiiRunner`, or return an empty state until real telemetry-backed analysis exists.

Do not show facility systems before analysis. Avoid hardcoded commercial pool or `Source / Intake` labels in active UI or API responses; systems should come from active analysis state and neutral domain profiles.
