# Shared Workspace Authorization — Architecture Discovery

Date: 2026-08-13
Status: phase-1 discovery

## Existing identity and scope boundary

- `backend/app/core/security.py` authenticates cookie sessions, service tokens, or development headers and binds a request-global `DatasetScope`.
- `backend/app/services/dataset_scope.py` currently derives `tenant_id` and `user_id` from the authenticated subject and accepts `X-Neraium-Workspace-Id` only as a data partition label. `DatasetScope.storage_id` hashes all three values. The header is not an authorization boundary.
- `backend/app/services/auth_store.py` is the authoritative identity directory. It supports SQLite for local/runtime and PostgreSQL (direct or Secrets Manager) for production. Roles are global `viewer`, `operator`, and `admin`; users can be active/inactive and sessions are revocable.
- The existing `workspace_id` is often a portfolio/data-partition label and can be identical for unrelated users. Dropping the user from the hash or trusting that label would merge formerly isolated data.
- The safe compatibility seam is to make an authorized workspace resolve to one canonical, immutable `DatasetScope`. All active members use that canonical resource scope while actor identity stays in `request.state.auth_context` for audit, assignment, and My Work.

## Persistence and migration model

- Auth schema is created in both `AUTH_SCHEMA_STATEMENTS` and `POSTGRES_AUTH_SCHEMA_STATEMENTS`, with ledgered migrations in `_apply_auth_schema_migrations`. Any membership model must work in both dialects.
- Runtime SQLite schema and migrations live in `backend/app/services/runtime_db.py`. Canonical maintenance records are `finding_cases` and append-only `finding_workflow_events`.
- Evidence/upload persistence is already partitioned by `DatasetScope.storage_id` in repository/object keys. A shared authorized workspace can reuse an existing historical partition by storing its canonical legacy scope tuple; no bulk rewrite of evidence blobs or finding event history is required.
- Existing users need a private default workspace bound to their current legacy `user/user/default` scope. Only that user is initially active. This preserves historical readability without broadening any account.
- Explicitly adding another active user to that workspace is the permission grant. Assignment remains a separate workflow event and cannot add membership.
- Membership removal must be a soft disable with timestamps/actor. Never delete the auth user, finding events, or historical assignment identity.

## Canonical finding workflow

- `backend/app/services/finding_workflow.py` materializes evidence/live sources into `finding_cases`, projects immutable workflow events, and provides list/detail/activity/mutation functions.
- Evidence findings copy `scope_storage_id` and `dataset_scope_json` from the evidence record. Detail, activity, list, and append paths compare against `current_dataset_scope().storage_id`.
- `list_finding_cases` scopes before in-memory workflow filters and pagination, but currently includes `scope_storage_id IS NULL`; historical/unscoped and live findings therefore need an explicit compatibility rule so new workspaces do not gain global data.
- `materialize_live_finding_cases` currently writes NULL scope, making live findings globally visible through the compatibility clause. New materialization must attach the current canonical scope; legacy NULL rows require a migration-safe quarantine/compatibility treatment.
- `_normalized_person_assignment` validates against all auth users, and `/api/findings/members` lists all active users. Both must use active membership in the current authorized workspace. Existing assignment event payloads stay untouched and readable after removal.
- `authorize_finding_action` keeps operators/admins as leads and viewers as technician-safe only when exactly assigned. Workspace membership must be checked before this role/action policy.
- Optimistic versions, append-only event triggers, terminal field-report guard, status transition rules, and actor strings are already authoritative and should remain unchanged.

## Evidence and related access paths

- `backend/app/routers/evidence.py` exposes evidence list/detail/integrity/latest/export/package/audit-tag/feedback/status. Several call `evidence_store` and upload repository fallbacks.
- `backend/app/services/runtime_db.py::list_evidence_runs_db` and `read_evidence_run_db` read rows without SQL scope predicates; protection is inconsistent and may happen only after payload loading. Scope must be validated before pagination/counting and before any direct-ID mutation.
- `read_evidence_run(run_id) or read_evidence_by_identity(run_id)` fallback paths must apply one identical current-workspace authorization test and return non-disclosing 404s.
- Related evidence packages, replay/job results, latest upload, facility context, package export, audit tags, feedback, and legacy compatibility mutations all need to resolve through the same canonical current resource scope.
- Existing compatibility mutations compare only `workspace_id` in places. Same workspace label across different users is not sufficient; compare the complete canonical scope/storage identifier.
- Resource lists/counts must filter by canonical scope before limit/offset. A post-pagination Python filter leaks counts and page shape.

## Frontend data boundary and routing

- Product-section routing (`activeWorkspace`) is distinct from the facility/data authorization workspace. UI/code should call the new concept `facilityWorkspace` or `authorizedWorkspace`.
- `frontend/src/config.js::apiFetch` already sends `X-Neraium-Workspace-Id` on all API requests; the server must validate it. `datasetSessionCache.js` already stores the selected data workspace, namespaces local cache by user/workspace, clears state on changes, and emits a workspace-change event.
- `/api/auth/me` and login can return active authorized workspace summaries and the selected/default workspace. The client must validate/reset stale local selection before runtime requests.
- A compact selector fits the existing engineering topbar/sidebar and only needs to appear for users with multiple active workspaces. Work should show a quiet `Facility workspace · <name>` label.
- `WorkQueueWorkspace` already relies on server-side `/api/findings` filters for My Work and Team Findings. Assignment UI posts stable member IDs. Making `/api/findings/members` workspace-scoped preserves the single canonical Work area.
- Denied `/work/:id` errors currently land in mutation state but are not rendered without a selected item. Add a dedicated detail loading/access-error state with a non-disclosing message.
- Unknown `/investigations/:id` and `/evidence/:id` currently fall back to `model.selectedFinding`; explicit IDs must exact-match scoped data or render the same clean unavailable state.
- Removed-member assignments with an `external_ref` disappear from the active picker and can be accidentally cleared. Render a disabled historical option and only send assignment when the lead intentionally changes it.
- `ObservationCenterWorkspace` uses `window.open` for evidence export, which omits the workspace header. Use authenticated `apiFetch` plus blob download.
- Generic GET fallback currently retries 404s against same-origin. Protected non-disclosing 404s must be authoritative to avoid querying a different backend candidate.

## Focused verification surfaces

- Backend: add `tests/test_workspace_authorization.py` for schema/backfill, A/B list/detail/activity/evidence/mutation denial, member assignment, disabled membership, historical attribution, role policy, terminal/stale guards, and pre-pagination scoping. Extend `tests/test_schema_migrations.py`, `tests/test_dataset_state_scoping.py`, and maintenance regressions where contracts change.
- Frontend: extend `findingsApi.test.js`, `datasetSessionCache`/config workspace tests, `WorkQueueWorkspace.test.js`, `EngineeringReasoningWorkspace.test.js`, and `GovernanceAdminWorkspace.test.js`.
- Browser: build on `frontend/tests/e2e/shared-maintenance-workflow.spec.js` with a focused workspace authorization spec for lead/technician/engineer/foreign user and 390px flow. Run `cd frontend && npm run setup:codex` first.
- Visual baselines are under `.planning/screenshots/shared-maintenance-workflow/`; new evidence belongs in `.planning/screenshots/shared-workspace-authorization/`.

## Architectural risks to close in design

1. Define deterministic private/default workspace backfill for SQLite and PostgreSQL without cross-user merging.
2. Define service-token and development-header compatibility without weakening strict session authorization.
3. Quarantine or explicitly bind legacy NULL-scoped live findings; never let a newly shared workspace inherit global rows silently.
4. Ensure auth-store membership availability and runtime data access fail closed in production.
5. Keep global account roles distinct from workspace membership state; do not introduce a second RBAC hierarchy.
