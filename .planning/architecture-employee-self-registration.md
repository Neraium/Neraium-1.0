# Architecture: Restricted Employee Self-Registration
> PRD: .planning/prd-employee-self-registration.md | Date: 2026-09-02

## Integration
- Replace pending-request contracts/routes/store/UI with one public registration endpoint.
- Validate configuration and code before entering the auth-store transaction.
- In one transaction, validate the configured workspace, insert a standard CPO user, and insert only that membership.
- Create the existing cookie session only after the registration transaction succeeds.

## Key Decisions
- **Workspace**: one required server-side UUID; no fallback or client field.
- **Authorization**: fixed internal `operator` permission for CPOs; no role field in the product flow.
- **Migration**: remove undeployed migration 004 and its pending-request table because self-registration uses existing user and membership tables.
- **Secret comparison**: `hmac.compare_digest` after verifying configuration is present.

## Verification
- Backend: registration security, storage, workspace, session, login/logout, and admin regression tests.
- Frontend: Create Profile validation, immediate authentication, API contract, and login regression tests.
- Package: lint, production build, `git diff --check`, one local commit.
