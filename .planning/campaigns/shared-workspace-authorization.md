# Campaign: Shared Workspace Authorization

Status: complete
Started: 2026-08-13T00:00:00Z
Direction: Introduce the smallest secure facility/workspace membership boundary so authorized maintenance users can share canonical findings, queues, investigation, and evidence without assignment granting access or unrelated workspaces leaking data.

## Claimed Scope

- `backend/app/`, `backend/tests/`
- `frontend/src/`, `frontend/tests/`, `frontend/e2e/`
- `docs/`
- `.planning/research/`, `.planning/screenshots/`, `.planning/review-packages/`

## Phases

1. [complete] Research: map auth identities, dataset scope, workflow/evidence persistence, runtime migrations, API paths, frontend routes, and test harness
2. [complete] Plan: specify the minimal migration-safe workspace membership and authorization design with explicit route matrix
3. [complete] Build: implement workspace schema, runtime migration, backend authorization, membership APIs, and focused tests
4. [complete] Build/Wire: implement workspace-aware queues, member assignment UX, access errors, investigation/evidence deep-link protection, and frontend tests
5. [complete] Verify: run backend focused/full, frontend Vitest/lint/build, Chromium desktop/mobile authorization flows, and visual review
6. [complete] Review/Package: run architecture/completion review, fix findings, document exact status and durable commit paths

## Phase End Conditions

| Phase | Required end conditions | validator_retries_remaining |
|---|---|---:|
| 1 | `file_exists:.planning/research/shared-workspace-authorization.md`; report maps all requested backend/frontend/test surfaces and identifies every relevant access path | 3 |
| 2 | `file_exists:.planning/research/shared-workspace-authorization-design.md`; design includes schema, migration/backfill, route authorization matrix, role rules, compatibility behavior, and explicit non-goals | 3 |
| 3 | `command_passes:PYTHONPATH=./backend ./.venv/bin/pytest -q backend/tests/test_workspace_authorization.py`; cross-workspace reads/mutations/evidence and invalid assignment are denied while historical attribution remains readable | 3 |
| 4 | `command_passes:cd frontend && npm test -- --run`; workspace queues, active-member assignment controls, clean access denial, and existing maintenance workflow have focused unit coverage | 3 |
| 5 | `command_passes:cd frontend && npm run build`; required backend/frontend suites and focused Chromium desktop plus 390px flows pass or have evidence-backed pre-existing failures | 3 |
| 6 | `file_exists:.planning/review-packages/shared-workspace-authorization.md`; `git diff --check` passes and an independent arbiter accepts correctness, security, migration safety, and architectural coherence | 3 |

## Exit Evidence

| Phase | Evidence type | Required | Artifact | Status |
|---|---|---:|---|---|
| 1 | doc | yes | `.planning/research/shared-workspace-authorization.md` | passed |
| 2 | doc | yes | `.planning/research/shared-workspace-authorization-design.md` | passed |
| 3 | test | yes | focused backend authorization/migration output in Feature Ledger | passed |
| 4 | test | yes | frontend unit output in Feature Ledger | passed |
| 5 | screenshot | yes | `.planning/screenshots/shared-workspace-authorization/` | passed |
| 5 | browser | yes | focused Chromium workspace flows | passed |
| 6 | review-package | yes | `.planning/review-packages/shared-workspace-authorization.md` | passed |

## Feature Ledger

| Feature | Status | Phase | Notes |
|---|---|---:|---|
| Architecture discovery | complete | 1 | Three read-only tracks mapped auth/schema, finding/evidence/data routes, frontend/deep links, and verification; phase validator passed |
| Secure workspace design | complete | 2 | Canonical resource scope, auth-store membership, evidence migration, fail-closed legacy behavior, API/UX contracts; validator passed |
| Backend authorization foundation | complete | 3 | Auth-store membership + request context, migration 010 evidence scope, exact findings/evidence access, same-workspace assignment; 39 focused tests passed; validator passed |
| Frontend workspace experience | complete | 4 | Full auth session/workspace switching, shared Work context, active-member assignment safety, admin membership, exact deep-link denials, and authenticated exports; 461 Vitest tests, lint, and build passed; phase validator passed |
| Integrated verification | complete | 5 | Final focused backend suite: 58 passed; frontend: 461 tests plus lint/build passed; combined Chromium suites: 8 passed. Default backend: 1,022 passed, 1 skipped, 20 deselected, 3 pre-existing failures reproduced exactly at clean baseline `533182e`; no budget changes; phase validator passed |
| Review and packaging | complete | 6 | Architecture review found no blocking boundary issue; binding completion arbiter accepted after independently passing 173 focused backend tests, frontend unit/lint/build, 8 Chromium flows, and diff-check |

## Decision Log

- 2026-08-13: Use the canonical `finding_cases` and `finding_workflow_events` plus existing auth identities.
  Reason: Required by product direction and prevents a competing workflow.
- 2026-08-13: Keep assignment and workspace authorization independent.
  Reason: Assignment must never become an implicit permission grant.
- 2026-08-13: Treat this as an amber, local-only campaign; do not commit, push, merge, deploy, or daemonize.
  Reason: The user prohibited remote changes and requested completion in the shared workspace.
- 2026-08-13: Explicit shared workspaces adopt an immutable existing DatasetScope instead of changing the storage hash.
  Reason: This shares historical data without merging unrelated users who used the same workspace label.
- 2026-08-13: Existing personal workspaces remain isolated; explicit `ws-*` membership is opt-in and never falls back when unauthorized.
  Reason: Historical compatibility must not silently broaden access.
- 2026-08-13: NULL-scoped findings/evidence fail closed for authenticated production access.
  Reason: Ownership cannot be inferred safely and NULL previously meant global visibility.

## Active Context

All six phases reached their handoff conditions. Binding completion review accepted the final tree. Direction check: aligned.

## Continuation State

Phase: complete
Sub-step: none
Files modified: `.planning/campaigns/shared-workspace-authorization.md`, `.planning/research/shared-workspace-authorization.md`, `.planning/research/shared-workspace-authorization-design.md`, `.planning/review-packages/shared-workspace-authorization.md`
Blocking: none
checkpoint-phase-1: none (preserving user-owned untracked `.planning` runtime files)
checkpoint-phase-2: none (preserving user-owned untracked `.planning` runtime files)
checkpoint-phase-3: none (preserving user-owned untracked `.planning` runtime files)
checkpoint-phase-4: none (preserving user-owned untracked `.planning` runtime files)
