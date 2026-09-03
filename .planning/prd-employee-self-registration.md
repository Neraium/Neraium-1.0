# PRD: Restricted Employee Self-Registration

> Description: Allow employees with an employer-issued code to self-register into one configured facility.
> Author: user
> Date: 2026-09-02
> Status: approved
> Mode: feature

## Core Features
1. Employees register with name, personal-or-work email, confirmed password, and an onboarding code.
2. The server validates the code and configured facility without exposing either value.
3. Registration atomically creates a `viewer` account and membership in only the configured workspace.
4. Successful registration establishes the existing HttpOnly session immediately.
5. Existing login, logout, admin account management, and workspace authorization remain unchanged.

## Out of Scope
- Public registration without the onboarding code.
- Employee-selected roles or workspaces.
- Multiple onboarding codes, invitations, or email-domain restrictions.

## Technical Decisions
- Read `NERAIUM_EMPLOYEE_ONBOARDING_CODE` and `NERAIUM_EMPLOYEE_ONBOARDING_WORKSPACE_ID` server-side because existing auth bootstrap secrets use environment configuration.
- Use the existing PBKDF2-SHA256 user storage and session cookie implementation.
- Fix the role to `viewer` and validate one exact active workspace before writing either the user or membership.

## End Conditions
- [ ] Valid registration creates one viewer, one configured membership, and one session.
- [ ] Invalid/missing code or workspace configuration creates nothing and issues no session.
- [ ] Extra role/workspace request fields are rejected.
- [ ] No password, hash, salt, or onboarding code is returned or logged.
- [ ] Focused auth tests, frontend tests, lint, build, and diff checks pass.
