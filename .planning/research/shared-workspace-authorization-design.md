# Shared Workspace Authorization — Implementation Design

Date: 2026-08-13
Decision: implement multiple explicit facility workspaces backed by immutable canonical legacy-compatible dataset scopes. Membership is authorization; global account role remains action policy.

## Security invariants

1. The browser workspace header selects but never authorizes a workspace.
2. An active account must have active membership in the active workspace before any facility resource is read, counted, paginated, exported, or mutated.
3. `viewer | operator | admin` remains the only RBAC hierarchy. Admin may manage membership but does not bypass operational workspace membership.
4. Assignment requires access but never grants it. A new person assignment requires an active auth account and active membership in the finding's current workspace.
5. Removed membership stops future reads and writes immediately. Actor and assignment snapshots in append-only events remain unchanged.
6. Cross-workspace explicit IDs return the same opaque 404 as nonexistent resources. Invalid-assignment validation happens only after finding authorization.
7. NULL/unscoped operational data is never globally visible in production.

## Auth-store schema and migration

Add dialect-equivalent SQLite/PostgreSQL tables to `AUTH_SCHEMA_STATEMENTS` and `POSTGRES_AUTH_SCHEMA_STATEMENTS`; add ledger entry `003_workspace_membership`:

```sql
auth_workspaces(
  workspace_id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  scope_tenant_id TEXT NOT NULL,
  scope_user_id TEXT NOT NULL,
  scope_workspace_id TEXT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP/TEXT NOT NULL,
  updated_at TIMESTAMP/TEXT NOT NULL,
  disabled_at TIMESTAMP/TEXT,
  created_by TEXT NOT NULL,
  UNIQUE(scope_tenant_id, scope_user_id, scope_workspace_id)
)

auth_workspace_members(
  workspace_id TEXT NOT NULL,
  email TEXT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  added_at TIMESTAMP/TEXT NOT NULL,
  updated_at TIMESTAMP/TEXT NOT NULL,
  disabled_at TIMESTAMP/TEXT,
  added_by TEXT NOT NULL,
  PRIMARY KEY(workspace_id,email),
  FOREIGN KEY(workspace_id) REFERENCES auth_workspaces(workspace_id) ON DELETE RESTRICT,
  FOREIGN KEY(email) REFERENCES auth_users(email) ON DELETE RESTRICT
)
```

Indexes: `(email,is_active)`, `(workspace_id,is_active)`. Scope tuple fields are immutable. Membership removal is an update, never delete.

Migration creates tables only. It does not add existing accounts to shared workspaces and therefore cannot broaden access.

### Workspace lifecycle

- Explicit IDs are opaque `ws-<uuid>` values, never user-provided legacy labels.
- Admin `POST /api/workspaces` creates a workspace and makes the actor its first active member. Default `adopt_current_scope=true` stores the actor's currently selected personal `DatasetScope` tuple, preserving existing findings/evidence/object keys without rewriting them.
- A new empty workspace can instead use `scope_tenant_id=workspace:<id>`, `scope_user_id=workspace:<id>`, `scope_workspace_id=default`.
- `POST /api/workspaces/{id}/members` activates/re-activates an existing active auth account.
- `POST /api/workspaces/{id}/members/{email}/disable` soft-disables membership. Prevent disabling the last active admin member and the caller's active membership in the current request.
- Workspace disable is out of scope for the initial UI; schema supports it.

### Personal compatibility

Existing accounts retain their historical personal scope when no explicit workspace ID is selected. `/api/auth/me` returns a synthetic personal workspace summary with ID `default`, name `Personal workspace`, and `kind=personal`; it resolves exactly to `tenant=user,user=user,workspace=default`. Other legacy workspace labels remain supported for the same authenticated owner only.

Explicit workspace IDs never fall back to personal resolution. Unknown `ws-*` or missing/disabled membership fails before operational storage access. This avoids colliding with historical label strings and preserves user isolation.

## Request resolution

Add `WorkspaceContext` and resolver functions in a small `workspace_authorization.py` service. `require_api_access` authenticates first, then resolves the requested header:

- Session identity: resolve explicit membership in every environment; otherwise personal compatibility scope.
- Development header identity: personal compatibility only unless the header subject maps to an active auth account with active explicit membership. Role bypass remains a development action-policy behavior, not membership bypass.
- Service token: personal service scope by default. Explicit `ws-*` access requires `NERAIUM_API_TOKEN_WORKSPACE_IDS` allowlisting; no admin wildcard.
- Public read-only endpoints retain anonymous personal scope and cannot read findings/evidence.

Set:

```text
request.state.auth_context.auth_subject = real actor email
request.state.workspace_context = {workspace_id, display_name, kind, membership_active}
request.state.dataset_scope = immutable canonical resource DatasetScope
```

The selected workspace is a resource boundary; the actor remains separate for `assigned_to_me`, action policy, audit, and event attribution.

Session/login payload gains `workspaces[]` and `default_workspace_id`. Each summary contains only `workspace_id`, `display_name`, `kind`, `is_active`; no backing scope tuple.

## Runtime evidence migration

Add runtime migration `010_workspace_evidence_scope`:

- Add `scope_storage_id TEXT` to `evidence_runs` on legacy databases and to fresh schema.
- Backfill scoped rows by parsing `payload_json.dataset_scope`, rebuilding the existing `DatasetScope`, and storing its existing `storage_id`.
- Leave truly unscoped records NULL; never infer ownership.
- Add `idx_evidence_runs_scope_created(scope_storage_id,created_at DESC,run_id DESC)`.
- Update `upsert_evidence_runs_db` to always persist the payload/current scope identifier.
- `list_evidence_runs_db`, `read_evidence_run_db`, event appends, history hydration, and cleanup accept/use exact scope. List SQL is `WHERE scope_storage_id=? ORDER BY ... LIMIT limit+1 OFFSET ?`.

Existing `finding_cases.scope_storage_id` remains the ownership field. Change all production reads/appends from `(scope_storage_id IS NULL OR scope_storage_id=?)` to exact equality. Do not rewrite `finding_workflow_events`.

New live finding materialization uses the current canonical scope. Migration
`011_workspace_live_analysis_scope` rebuilds live configurations, runs, findings, and
health with scope-aware natural uniqueness and composite run/finding integrity. All
live reads, writes, background due-work selection, and pagination use exact scope.
Legacy NULL live rows remain inaccessible until an explicit future admin adoption tool;
the product does not guess.

## Backend API and authorization matrix

New routes (`routers/workspaces.py`, all require auth):

- `GET /api/workspaces` — active workspaces for caller plus personal compatibility summary.
- `GET /api/workspaces/current/members` — safe projections for current workspace; all members may read, active by default.
- `POST /api/workspaces` — admin; create/adopt.
- `POST /api/workspaces/{id}/members` — admin; active existing account only.
- `POST /api/workspaces/{id}/members/{email}/disable` — admin; soft disable.

`GET /api/findings/members` delegates to current active workspace members. It never lists global accounts.

| Surface | Workspace rule | Role/action rule |
|---|---|---|
| finding list/detail/activity | exact current canonical scope before filters/pagination | any active member |
| finding workflow/field report | authorize finding first | existing viewer-assignee/operator/admin rules |
| assignment/priority/due/guidance/review | exact finding scope, then validate assignment membership | operator/admin |
| evidence list/latest/detail/integrity | exact scope at DB query | any active member |
| evidence export/package/audit/feedback/status | exact scope before mutation/export | preserve existing operator dependency |
| upload/latest/status/stream/replay/intake | current canonical DatasetScope and payload equality | existing route role |
| analyses/packages/related/fingerprint/lifecycle | current canonical DatasetScope | existing route role |
| facility context | current canonical DatasetScope | existing route role |
| membership management | explicit workspace exists | admin, without data-access bypass |

For canonical findings, source materialization first restricts evidence rows to the current scope. Workflow filters occur after scope and before returned pagination. Where projection filters cannot be expressed in SQL immediately, load only current-scope candidates and paginate the filtered result; no foreign row affects counts/page shape.

Legacy evidence status/feedback compares full `DatasetScope.storage_id`, not `workspace_id`, and person assignment resolves an active current-workspace member ID. New label-only assignment writes are rejected; old label-only events remain projectable.

## Frontend contract

- `App` retains the enriched user/workspace session payload.
- Before authenticated runtime mounts, validate local selected workspace against returned active summaries; reset to `default_workspace_id` and activate its cache scope if stale.
- Add a compact facility workspace selector in the engineering topbar/account region only when multiple choices exist. On change call `setCurrentWorkspaceId`, clear scoped cache through existing helpers, and remount via `datasetScopeKey`.
- Work header shows `Facility workspace · <name>`. My Work remains assignment-to-current-actor; Team Findings is the same shared queue.
- Assignment controls consume only current active member summaries. If a historical assignment is absent from the active list, render a disabled `Former member · historical assignment` option and do not submit assignment until changed intentionally.
- Add a dedicated work-detail loading/error state. Treat 403 and opaque 404 as `This finding is unavailable in the current facility workspace`; do not display ID/evidence metadata.
- Explicit investigation/evidence route IDs must exact-match scoped loaded/canonical data. Never fall back to the default finding.
- Replace direct `window.open` evidence export with `apiFetch` blob download so the workspace header is included.
- Protected API GET 404 responses are authoritative and must not trigger a second backend candidate.
- Add a compact Current facility membership block inside existing Access & governance. Distinguish global account status from workspace access.

## Implementation order

1. `auth_store.py`, workspace service/models/routes, security resolver, auth/session contracts and tests.
2. `runtime_db.py`, `evidence_store.py`, finding exact-scope/assignment enforcement, evidence/data compatibility route tests.
3. Frontend session/cache/config switch, Work errors/historical assignment, admin membership, exact deep links/export.
4. Unit/full suites, Chromium desktop and 390px flows, screenshots, independent architecture/security review.

## Verification

- Focused backend: `PYTHONPATH=./backend ./.venv/bin/pytest -q tests/test_workspace_authorization.py tests/test_schema_migrations.py tests/test_shared_maintenance_workflow.py tests/test_finding_workflow.py tests/test_finding_lifecycle.py`
- Full backend: `PYTHONPATH=./backend ./.venv/bin/pytest -q`
- Frontend: `cd frontend && npm test -- --run && npm run lint && npm run build`
- Browser setup: `cd frontend && npm run setup:codex`
- Chromium: `cd frontend && npm run test:e2e -- --config=playwright.codex.config.js --project=chromium tests/e2e/workspace-authorization.spec.js tests/e2e/shared-maintenance-workflow.spec.js`
- Repository: `git diff --check`, inspect full `git diff`, and compare failures with baseline.

## Explicit non-goals and remaining gaps

- No workspace-specific roles, invitations, SSO groups, platform-superadmin bypass, physical dispatch/control, or second finding/work system.
- No automatic sharing/backfill across existing accounts.
- Ambiguous NULL legacy records are fail-closed and require a future audited adoption tool.
- Facility-scoped operational audit/queue observability is still limited by older global runtime tables. Evidence-derived observability is scoped; platform-wide queue/audit totals remain administrator diagnostics and are not exposed in Work queues.
