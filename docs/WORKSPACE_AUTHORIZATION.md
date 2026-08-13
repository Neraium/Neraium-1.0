# Facility Workspace Authorization

Neraium facility workspaces let a maintenance organization share the existing
canonical finding and evidence workflow without making assignment a permission grant.
The implementation remains read-only with respect to physical infrastructure.

## Boundary and policy

- An explicit facility has an opaque `ws-<uuid>` ID and an immutable backing
  `DatasetScope`.
- An active account needs an active `auth_workspace_members` row before the server
  resolves that facility scope.
- The `X-Neraium-Workspace-Id` header selects a workspace; it never authorizes one.
- Existing `viewer`, `operator`, and `admin` roles continue to govern actions. Membership
  governs data access. Admin does not bypass membership.
- Assignment is validated only after finding authorization and may target only an active
  account with active membership in the same facility.
- Disabling membership revokes future access without deleting actor, assignment, field
  report, or activity history.
- Cross-workspace IDs and absent IDs are both opaque 404 responses. Scope filtering is
  applied before filtering, counts, and pagination.

Existing accounts retain a synthetic private `default` workspace. Migration does not
enroll any account into a shared facility and does not merge accounts that previously
used the same browser workspace label.

## Storage

The auth store adds:

- `auth_workspaces`, including the immutable backing scope tuple;
- `auth_workspace_members`, with soft-disable state and historical timestamps;
- auth migration ledger entry `003_workspace_membership`.

The runtime database adds:

- `010_workspace_evidence_scope`, which indexes evidence by exact scope and backfills
  only payloads carrying an authoritative DatasetScope;
- `011_workspace_live_analysis_scope`, which rebuilds live configurations, runs,
  findings, and health with scope-aware uniqueness and integrity.

Canonical `finding_cases` and append-only `finding_workflow_events` remain the only Work
system. NULL or malformed historical scopes remain stored but inaccessible; ownership is
never inferred from the first reader.

## Administration and API

An admin creates a facility with `POST /api/workspaces`. By default,
`adopt_current_scope=true` adopts the selected personal data scope so existing scoped
findings and evidence become the facility's initial history without rewriting object
keys. The creator becomes its first member. The UI currently manages membership after
the facility exists; initial facility creation is an API/provisioning action.

Membership routes are:

- `GET /api/workspaces`
- `GET /api/workspaces/current/members`
- `POST /api/workspaces`
- `POST /api/workspaces/{workspace_id}/members`
- `POST /api/workspaces/{workspace_id}/members/{email}/disable`

The add route accepts an existing active auth account. Adding a removed member reactivates
membership. Disabling is a soft update and the last active admin cannot be removed.
Service-token access to an explicit facility requires the exact ID in
`NERAIUM_API_TOKEN_WORKSPACE_IDS`; there is no wildcard.

## Product behavior

The session payload lists only the caller's active workspace summaries. The frontend
validates local selection against that list, scopes caches by user and workspace, and
remounts facility state when selection changes. Work shows one shared Team Findings
queue plus actor-filtered My Work. Assignment controls use only active current-facility
members and preserve removed assignees as historical display values.

Finding, activity, investigation, evidence, export, upload, replay, facility context,
and live-analysis paths resolve through the same server-owned DatasetScope. Direct links
show a clean unavailable state and do not fall back to another finding.

## Known limitations

- Initial workspace creation is provisioned through the API; the current admin UI covers
  member add/reactivate/disable, not facility naming or disablement.
- Account roles are global rather than workspace-specific.
- Ambiguous historical NULL-scoped data needs a future audited adoption/quarantine tool.
- Older platform queue and audit observability totals are global administrator
  diagnostics; facility Work counts, rows, activity, and evidence metadata are scoped.
