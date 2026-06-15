# Upload State Integrity Refactor

## Root Cause Analysis

Upload state drift came from multiple partially-overlapping sources of truth.

Before this refactor:
- completed upload state could be reconstructed from different persisted files, shared state keys, replay payloads, and UI session caches
- `latest-upload` could infer a current upload from stale summaries, historical job entries, or prior persisted output even when no current upload was active
- replay could fall back to unrelated global state and surface frames from the wrong run
- frontend session restoration could prefer cached or historical job identifiers over the current persisted upload identity
- upload lifecycle writes were spread across job status updates, summary writes, result writes, and evidence persistence without a single canonical contract

This created a class of bugs where Gate, Findings, Supporting Evidence, Evidence Replay, and session restoration could disagree about which upload they were representing.

## Stale-State Leakage Explanation

The main stale-state leakage paths were:
- summary-only persisted state that outlived the active upload it once described
- replay fallback to process-global intelligence state when a newer queued upload existed
- session restoration reading `history[0]` or prior local state as a substitute for a current upload
- shared-state lookups that reused prior result/evidence identity without explicit upload validation
- implicit cache resets that did not consistently clear all in-memory latest-upload views

The refactor suppresses these paths by requiring a valid canonical upload identity before exposing completed findings, replay, or evidence-backed status.

## Canonical Upload Object Definition

A single canonical persisted object now represents the latest upload lifecycle state: `latest_upload.json` plus its mirrored shared-state entry.

Core fields:
- `status`
- `message`
- `upload_id`
- `job_id`
- `run_id`
- `filename`
- `session_scope`
- `traceability`
- `summary`
- `result`
- `replay`
- `evidence`
- `updated_at`
- `version`

Rules:
- completed views derive from this canonical object
- completed findings are exposed only when the canonical record contains a valid completed result aligned to the same `upload_id`/`job_id`/`run_id`
- queued or processing uploads remain visible as current upload state, but do not inherit findings or replay from prior runs
- no-current-upload state returns an explicit empty snapshot rather than reconstructing from stale history

## Architecture Before

Before:
- `latest-upload` reconstructed state from summary files, per-job records, latest result, history, and fallback caches
- replay used uploaded replay when available but could fall back to unrelated global intelligence state even when the current upload context had changed
- frontend restoration could derive session identity from historical jobs
- cache invalidation was partial and non-obvious

## Architecture After

After:
- upload lifecycle writes converge through canonical record builders in `backend/app/services/upload_jobs.py`
- `latest-upload` resolves from the canonical persisted upload record and only exposes completed findings/evidence when identity alignment is valid
- replay prefers upload-scoped canonical replay and only falls back to global replay when there is no current canonical upload session at all
- frontend session restoration resolves from canonical upload identity, not stale history
- queued/processing uploads explicitly clear stale completed result exposure

## Changed Files

Backend:
- `backend/app/services/upload_jobs.py`
- `backend/app/routers/data.py`
- `backend/app/routers/replay.py`

Frontend:
- `frontend/src/viewModels/currentSession.js`
- `frontend/src/components/DataConnectionsWorkspace.jsx`
- `frontend/src/components/replay/ReplayWorkspace.test.js`
- `frontend/src/viewModels/__tests__/currentSession.test.js`

Tests:
- `tests/test_data_upload.py`
- `tests/test_replay_api.py`

Documentation:
- `docs/upload_state_integrity_refactor.md`

## Tests Added

Added or tightened lifecycle coverage for:
- no active session returns empty latest-upload state without `relationship_drift`
- completed upload identity alignment across latest-upload, findings/evidence, and replay
- queued replacement upload suppresses prior completed findings
- replay does not fall back to stale global state when a current queued upload exists
- frontend current-session resolution does not reuse stale history
- replay fixtures include aligned upload/job/run lineage for evidence-backed rendering

## Validation Results

Validated during refactor:
- `git diff --check`
- `python3 -m py_compile backend/app/services/upload_jobs.py backend/app/routers/data.py backend/app/routers/replay.py`
- `cd /home/ubuntu/Neraium-1.0 && PYTHONPATH=./backend ./.venv/bin/pytest -q tests/test_data_upload.py -k 'latest_upload or canonical_identity or suppresses_prior or no_active_session'`
- `cd /home/ubuntu/Neraium-1.0 && PYTHONPATH=./backend ./.venv/bin/pytest -q tests/test_replay_api.py`
- `cd /home/ubuntu/Neraium-1.0 && PYTHONPATH=./backend ./.venv/bin/pytest -q tests/test_data_upload.py tests/test_replay_api.py tests/test_data_replay.py tests/test_messy_upload_reliability.py`
- `cd /home/ubuntu/Neraium-1.0/frontend && npm test -- --run src/viewModels/__tests__/currentSession.test.js src/components/replay/ReplayWorkspace.test.js src/components/OnboardingWorkspace.upload.test.js src/App.test.js`
- `cd /home/ubuntu/Neraium-1.0/frontend && npm run build`

Final exact command results are recorded from the terminal run in the completion report.

## Remaining Risks

- The canonical latest-upload contract now intentionally suppresses summary-only completed states when no aligned result exists. Any remaining callers that depended on summary-only completion may need follow-up cleanup.
- `upload_jobs.py` has clearer boundaries than before, but it still contains multiple lifecycle responsibilities. This refactor reduced drift without attempting a risky rewrite.
- Some legacy shared-state compatibility bridges remain in place so older call paths can still populate the canonical object. Those bridges should eventually be retired once all callers are consolidated.
