# PRD: Restricted Employee Self-Registration

> Description: Allow employees to register through administrator-issued, single-use facility invitations.
> Author: user
> Date: 2026-09-02
> Status: approved
> Mode: feature

## Core Features
1. Administrators create expiring, single-use links bound to their selected facility.
2. Employees register with name, personal-or-work email, and a confirmed password from that link.
3. Registration atomically creates a standard CPO account and membership in only the invitation workspace.
4. Successful registration establishes the existing HttpOnly session immediately.
5. Existing login, logout, admin account management, and workspace authorization remain unchanged.

## Out of Scope
- Public registration without a valid invitation.
- Employee-selected roles or workspaces.
- Multiple onboarding codes, invitations, or email-domain restrictions.

## Technical Decisions
- Store only a SHA-256 invite-token digest and return the raw token once to the creating administrator.
- Use the existing PBKDF2-SHA256 user storage and session cookie implementation.
- Use the existing internal `operator` permission for every CPO and expose no role choice during onboarding.

## End Conditions
- [ ] Valid registration creates one standard CPO account, one configured membership, and one session.
- [ ] Invalid, expired, revoked, reused, or missing invitations create nothing and issue no session.
- [ ] Extra role/workspace request fields are rejected.
- [ ] No password, hash, salt, or onboarding code is returned or logged.
- [ ] Focused auth tests, frontend tests, lint, build, and diff checks pass.
