# Architecture: Employee Account Requests
> PRD: .planning/prd-employee-account-requests.md | Date: 2026-09-02

## File Tree
- `backend/app/services/auth_store.py` — extend schema and transactional request lifecycle.
- `backend/app/models/api_models.py` — request/review contracts and safe response projections.
- `backend/app/routers/auth.py` — public submit plus admin list/approve/reject routes.
- `tests/test_employee_account_requests.py` — end-to-end API and authorization coverage.
- `frontend/src/services/api/authApi.js` — public request client.
- `frontend/src/components/AuthScreen.jsx` — login/request/pending views.
- `frontend/src/components/AuthScreen.test.js` — employee flow coverage.
- `frontend/src/components/GovernanceAdminWorkspace.jsx` — admin review controls.
- `frontend/src/components/GovernanceAdminWorkspace.test.js` — admin interaction coverage.
- `frontend/src/styles/auth-premium.css` — scoped request-form styling.

## Component Breakdown
### Request lifecycle
- Files: auth store, models, router | Dependencies: existing auth/workspace store | Complexity: high

### Employee access UI
- Files: auth API, AuthScreen, auth styles | Dependencies: existing login shell | Complexity: medium

### Admin review UI
- Files: GovernanceAdminWorkspace and tests | Dependencies: existing User Access panel | Complexity: medium

## Data Model
### Account request
- Fields: request_id, normalized email, first_name, last_name, salt, password_hash, status, created_at, reviewed_at, reviewed_by, approved_role, approved_workspace_id.
- Relationships: approval materializes one auth user and one explicit workspace membership.

## Key Decisions
### Approval transaction: auth-store atomic operation
- **Chosen**: Create user, membership, and review state in one database transaction to prevent partial authority grants.
- **Rejected**: Chain existing HTTP endpoints from the frontend because failure could leave a partially approved account.

### Workspace assignment: one explicit facility workspace
- **Chosen**: Require a workspace ID authorized to the reviewing admin; this is narrow and auditable.
- **Rejected**: Automatic or all-workspace access because it grants unrequested authority.

### Pending login message: verify submitted password
- **Chosen**: Return the pending message only when the pending request password matches.
- **Rejected**: Reveal pending status by email alone because it enables account enumeration.

## Build Phases
### Phase 0: Baseline
- **Goal**: Record current auth behavior.
- **End Conditions**: focused backend and frontend auth tests pass.

### Phase 1: Backend lifecycle
- **Goal**: Add secure storage, public submission, pending login, and admin adjudication.
- **End Conditions**: targeted backend request tests pass; existing auth tests pass.

### Phase 2: Frontend flows
- **Goal**: Add employee request and admin review experiences.
- **End Conditions**: targeted frontend auth/admin tests pass; lint and build pass.

### Phase 3: Package
- **Goal**: Review diff and create one coherent commit.
- **End Conditions**: `git diff --check` passes and the worktree contains only expected pre-existing untracked paths after commit.

## Phase Dependency Graph
Phase 0 -> Phase 1 -> Phase 2 -> Phase 3

## Risk Register
1. Partial approval: use a single datastore transaction.
2. Account enumeration: use generic duplicate responses and require password verification for pending-login detail.
3. Overbroad workspace access: require one explicit admin-authorized facility workspace.
4. Regression in existing authentication: retain session endpoints and run focused baseline tests again.
