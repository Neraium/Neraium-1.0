# Review Package: Shared Facility Workspace Authorization

Date: 2026-08-13
Campaign: `.planning/campaigns/shared-workspace-authorization.md`
Status: accepted

## Objective

Make canonical Neraium findings, maintenance queues, investigation, and evidence
collaborative inside an explicit facility boundary while keeping unrelated facilities
isolated. Assignment remains workflow metadata and never grants data access.

## Implemented architecture

```text
authenticated actor
        |
        v
active auth_workspace_members row  -- no --> opaque 404
        |
        v
workspace immutable backing DatasetScope
        |
        +--> uploads / packages / replay / facility context
        +--> evidence_runs (exact scope before LIMIT/OFFSET)
        +--> live analysis (exact scope before reads/due work)
        +--> finding_cases + append-only workflow events
                         |
                         v
             global role/action policy
             viewer self-assignee | operator | admin
```

The actor identity is retained separately for My Work, audit, optimistic-lock events,
field reports, and historical attribution. The browser header selects a facility but the
server resolves membership and backing scope on every request.

## Schema and migration

- Auth migration `003_workspace_membership` adds `auth_workspaces` and soft-disable
  `auth_workspace_members` for both SQLite and PostgreSQL auth backends.
- Runtime migration `010_workspace_evidence_scope` adds exact evidence scope and a
  scope-first created-time index. Only authoritative payload scopes are backfilled.
- Runtime migration `011_workspace_live_analysis_scope` rebuilds live configuration,
  run, finding, and health tables with scope-aware uniqueness and a composite scoped
  run/finding foreign key. Legacy NULL rows are retained and fail closed.
- Existing `finding_cases` and append-only `finding_workflow_events` remain canonical.
  Their read/write paths now require exact scope; event attribution is not rewritten.
- No account is automatically enrolled and no historical scope is guessed.

## Authorization rules reviewed

- Active account plus active membership is required for every explicit workspace read
  and mutation. Membership disable takes effect on the next request.
- Existing personal scopes remain isolated. An explicit `ws-*` denial never falls back
  to a personal scope.
- `viewer`, `operator`, and `admin` remain global action roles. Admin does not bypass
  workspace membership.
- Only an active member of the current workspace may be newly assigned. Removed-member
  assignments remain readable; label-only new assignments are rejected.
- A production viewer can update only a finding assigned exactly to their active member
  identity and cannot perform lead feedback/resolution/assignment mutations.
- Resource scope is resolved before action policy on security-sensitive finding/evidence
  mutations, making foreign and missing IDs indistinguishable.
- Service-token selection of an explicit workspace requires an exact environment
  allowlist entry.
- NULL evidence/live source rows are not claimable by the first reader.

## API changes

New:

- `GET /api/workspaces`
- `GET /api/workspaces/current/members`
- `POST /api/workspaces`
- `POST /api/workspaces/{workspace_id}/members`
- `POST /api/workspaces/{workspace_id}/members/{email}/disable`

Changed:

- login and `/api/auth/me` include active workspace summaries and a default workspace;
- `/api/findings/members` returns only active current-workspace members (only the owner
  in a personal scope);
- findings, activity, workflow, field reports, feedback, and resolution require exact
  canonical scope;
- evidence list/detail/latest/integrity/export/package/status/feedback/audit paths use
  exact evidence scope;
- live-analysis configuration/run/finding/health reads, mutations, deduplication, and due
  processing use exact scope;
- protected resource 404s remain authoritative in the frontend API fallback layer.

## Frontend changes

- The app retains the full auth session, validates stale browser workspace selection,
  scopes caches by actor/workspace, and remounts runtime state on an authorized switch.
- A compact facility label/selector appears without overloading the existing product-area
  navigation concept also called workspace.
- Work presents one shared Team Findings queue and an actor-filtered My Work view.
- Assignment controls contain active current-facility members only, expose member-load
  failure, and preserve removed assignees without silently clearing them.
- Work, investigation, and evidence deep links require an exact scoped finding. Denials
  show a clean unavailable state without IDs, counts, evidence metadata, or fallback to a
  default analytical finding.
- Evidence downloads use authenticated blob requests so the workspace header is present.
- Access administration separates global account state from current-facility membership.

## Verification evidence

- Final focused backend authorization, membership, migration, live-analysis,
  finding-lifecycle, and OpenAPI suite: 58 passed, 1 warning.
- Frontend Vitest: 55 files, 461 tests passed.
- Frontend ESLint: passed.
- Frontend production build: passed without budget changes.
- Combined Chromium workspace-authorization and existing shared-maintenance suites:
  8 passed in 24.3 seconds, including the required 390px technician flow.
- Browser setup used the repository-locked `npm run setup:codex` path.
- `git diff --check`: passed on the final tree.

Repository-wide default backend suite notes:

- Final `PYTHONPATH=.:./backend ./.venv/bin/pytest -q`: 1,022 passed, 1 skipped,
  20 deselected, 3 failed, and 32 warnings in 1,914.30 seconds.
- The remaining failures are two telemetry terminal-state polling simulations and the
  upload robustness benchmark. No performance budget was loosened.
- The exact three failing tests were rerun from detached clean baseline commit
  `533182e` in a temporary worktree and produced the same three failures (with one pass),
  demonstrating that they pre-exist this change rather than regress from workspace
  authorization. The baseline worktree was removed afterward.

## Visual evidence

- `.planning/screenshots/shared-workspace-authorization/lead-assignment-desktop.png`
- `.planning/screenshots/shared-workspace-authorization/technician-complete-desktop.png`
- `.planning/screenshots/shared-workspace-authorization/engineer-evidence-desktop.png`
- `.planning/screenshots/shared-workspace-authorization/unauthorized-workspace-denial.png`
- `.planning/screenshots/shared-workspace-authorization/technician-390.png`

The screenshot folder is explicitly unignored for this review package. Visual inspection
confirmed the existing graphite/blue language, progressive technical evidence, a clean
opaque denial, touch-sized technician controls, and no 390px horizontal overflow.

## Known limitations / follow-up

- Initial facility creation/adoption is an admin API/provisioning action. The current UI
  manages membership after creation but does not name, disable, or delete facilities.
- Roles remain global rather than workspace-specific; this release intentionally avoids
  a second RBAC system.
- Ambiguous historical NULL-scoped evidence/live data requires a future audited adoption
  or quarantine tool. It remains stored and inaccessible now.
- Platform queue and audit observability totals are older global admin diagnostics.
  Facility Work counts, queue rows, finding activity, and evidence metadata are scoped.
- No invitation/SSO-group provisioning or workspace-specific service accounts.
- No physical dispatch, write-back, or infrastructure control was introduced.

## Independent review

Read-only architecture/security pass against the implemented diff, project structure,
and the design documents in `.planning/research/` found no blocking architecture or
authorization-boundary violations in the changed files.

Reviewed areas:

- auth-store membership schema and both SQLite/PostgreSQL paths;
- request workspace resolution and context propagation;
- canonical finding/evidence/live-analysis exact-scope enforcement;
- resource-before-role ordering on sensitive routes;
- personal-scope preservation and explicit-workspace fail-closed behavior;
- frontend session/header/cache/deep-link/export handling.

Non-blocking review notes:

- The repo does not contain a top-level `CLAUDE.md` or `.claude/rules/` tree, so the
  architecture pass used the existing repository structure plus the feature design docs
  rather than project-local architecture rule files.

## Completion arbiter

Binding verdict: **ACCEPT**.

The independent arbiter reran `git diff --check`, 173 focused backend tests, focused
frontend unit tests, frontend lint/build, repository-locked browser setup, and both
Chromium workspace/maintenance suites (8 passed). It independently confirmed request-
level membership resolution, assignment/authorization separation, resource-before-role
denials, exact persistence scope, mirror fallback safety, and frontend workspace/deep-
link/export coherence. Its only non-blocking note was that it relied on this package's
recorded clean-baseline reproduction rather than rerunning the 32-minute full suite.
- Older platform-wide observability/admin diagnostics remain global by design; the
  scoped work queue, activity, and evidence surfaces introduced here are workspace
  constrained.
