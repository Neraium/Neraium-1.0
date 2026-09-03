# PRD: Employee Account Requests

> Description: Add administrator-approved employee onboarding to the existing PPC authentication system.
> Author: user
> Date: 2026-09-02
> Status: approved
> Mode: feature

## Problem
Employees need a safe way to request PPC App access without enabling unrestricted public account creation.

## Users
- Employees requesting access.
- Administrators reviewing and assigning access.

## Core Features
1. Account request: An unauthenticated employee submits name, work email, and a confirmed password without receiving a session or authority.
2. Pending state: A submitted request remains non-authenticated until reviewed.
3. Admin review: Administrators list, approve, or reject pending requests.
4. Explicit authorization: Approval assigns an existing role and one explicitly selected facility workspace.
5. Existing login: Approved employees use the current secure cookie-session login flow.

## Out of Scope (v1)
- Public self-registration or automatic workspace selection.
- Invitations, email delivery, password reset, and account recovery.
- Changes to unrelated application routing or telemetry architecture.

## Technical Decisions
- **Auth storage**: Extend the existing dual SQLite/PostgreSQL auth store because it already owns users, password hashing, sessions, and memberships.
- **Passwords**: Store the existing PBKDF2-SHA256 salt/hash material on pending requests so plaintext never persists and approval does not require password recovery.
- **Authorization**: Require an authenticated administrator and an explicit authorized facility workspace for approval because requesters cannot grant their own authority.
- **Deployment**: Use the existing startup-managed auth schema migration path; no new service or environment variable is required.

## Architecture
The public auth router accepts request submissions and stores only pending credentials and profile data. Admin-protected endpoints list and adjudicate requests through the existing auth store. Approval atomically creates the user, grants one selected workspace membership, and closes the request. The current login/session path remains the only way to authenticate.

## Integration Points
- **Existing files modified**: auth store, auth API models/router, login screen/API/styles, governance admin UI/tests.
- **New files created**: targeted backend request-flow test and these planning records.
- **Dependencies added**: none.
- **Patterns followed**: FastAPI contracts, auth-store abstractions, runtime schema migrations, React stateful panels, existing role/workspace authorization.

## End Conditions (Definition of Done)
- [ ] A valid public request persists without creating a user, membership, or session.
- [ ] Duplicate active accounts and unresolved requests are rejected safely.
- [ ] Pending credentials receive an approval-pending login response but no session.
- [ ] Only administrators can list or adjudicate requests.
- [ ] Approval creates an account with the selected role and explicit workspace membership.
- [ ] Rejection leaves the requester unable to authenticate.
- [ ] Password hashes and salts never appear in API responses.
- [ ] Existing focused auth tests pass with no new failures.
- [ ] Frontend lint and production build pass with no new errors.

## Open Questions
None.
