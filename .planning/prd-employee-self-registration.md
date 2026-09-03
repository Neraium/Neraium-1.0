# PRD: Restricted Employee Self-Registration

> Description: Allow employees to register through one administrator-issued, reusable company signup link.
> Author: user
> Date: 2026-09-02
> Status: approved
> Mode: feature

## Core Features
1. Administrators create one expiring, reusable company-wide signup link without selecting a facility.
2. Employees register with name, personal-or-work email, and a confirmed password from that link.
3. Registration atomically creates a standard CPO account with only its built-in personal workspace.
4. Successful registration establishes the existing HttpOnly session immediately.
5. Existing login, logout, admin account management, and workspace authorization remain unchanged.

## Out of Scope
- Public registration without a valid invitation.
- Employee-selected roles or workspaces.
- Facility-bound invitations, onboarding codes, or email-domain restrictions.

## Technical Decisions
- Store only a SHA-256 signup-token digest and return the raw link once to the creating administrator.
- Creating a replacement link revokes the previous company link.
- Use the existing PBKDF2-SHA256 user storage and session cookie implementation.
- Use the existing internal `operator` permission for every CPO and expose no role choice during onboarding.

## End Conditions
- [ ] Valid registration creates standard CPO accounts and sessions from the reusable link without facility membership.
- [ ] Invalid, expired, revoked, or missing links create nothing and issue no session.
- [ ] Extra role/workspace request fields are rejected.
- [ ] No password, hash, salt, or onboarding code is returned or logged.
- [ ] Focused auth tests, frontend tests, lint, build, and diff checks pass.
