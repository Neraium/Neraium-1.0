# Architecture: Restricted Employee Self-Registration
> PRD: .planning/prd-employee-self-registration.md | Date: 2026-09-02

## Integration
- Add admin invitation create/list/revoke endpoints and a public registration endpoint.
- Validate and lock the hashed invitation inside the registration transaction.
- In one transaction, consume the invite, insert a standard CPO user, and insert only its bound membership.
- Create the existing cookie session only after the registration transaction succeeds.

## Key Decisions
- **Workspace**: bound by the administrator at invite creation; no employee field.
- **Authorization**: fixed internal `operator` permission for CPOs; no role field in the product flow.
- **Migration**: remove undeployed migration 004 and its pending-request table because self-registration uses existing user and membership tables.
- **Token storage**: SHA-256 digest only; random raw token returned once and removed from the browser URL.

## Verification
- Backend: invitation lifecycle, registration security, workspace, session, login/logout, and admin regression tests.
- Frontend: Create Profile validation, immediate authentication, API contract, and login regression tests.
- Package: lint, production build, `git diff --check`, one local commit.
