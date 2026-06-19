# Production Acceptance Checklist

Use this as the final go or no-go checklist for investor demos, controlled pilots, and production/operator use.

## Smoke Endpoints

- [ ] `GET /api/health` returns success.
- [ ] `GET /api/ready` returns success.
- [ ] `GET /api/observability/metrics` returns metrics or documented auth warning.
- [ ] Smoke script detects no HTML error pages.
- [ ] API response headers include expected security headers.

## Operator Flow

- [ ] Upload CSV passes.
- [ ] Upload JSON or TXT telemetry path passes where supported.
- [ ] API config flow passes.
- [ ] Test Connection passes.
- [ ] Poll Once passes.
- [ ] Start Polling passes and duplicate polling is prevented.
- [ ] Stop Polling works cleanly.
- [ ] Evidence Trail opens and explains what changed.
- [ ] Historical Replay opens and shows available evidence history.
- [ ] Export Evidence succeeds and contains traceable metadata.
- [ ] Empty states never display fake conclusions.
- [ ] Loading states clearly distinguish waiting, processing, complete, failed, and unavailable.

## Guardrails

- [ ] Oversize upload returns 413.
- [ ] Queue saturation returns 503 or is documented as safely tested only in staging/local.
- [ ] Rejected uploads do not create fake completed evidence.
- [ ] Recovery after guardrail rejection is confirmed.
- [ ] Failed upload job status is visible and does not stall indefinitely.
- [ ] Worker restart recovery is tested with at least one queued job.

## SII Source Of Truth

- [ ] No production dashboard output is fabricated in the frontend.
- [ ] Missing SII output shows "Awaiting SII analysis" or equivalent neutral state.
- [ ] Operational conclusions are evidence-linked.
- [ ] Runway or projected time-to-failure is shown only when provided by backend/SII output.
- [ ] Sample mode is explicitly labeled and never silently replaces production output.
- [ ] SII result includes limitations or confidence basis when confidence is low.
- [ ] Replay views use persisted backend artifacts, not client-only reconstruction.

## Authentication And Authorization

- [ ] Login, logout, and `/api/auth/me` work over HTTPS.
- [ ] Session cookies are `HttpOnly`.
- [ ] Session cookies are `Secure` in HTTPS production.
- [ ] Session cookie `SameSite` behavior is documented.
- [ ] Login failures do not reveal whether a user exists.
- [ ] Login route has rate limiting, WAF protection, or documented temporary mitigation.
- [ ] Admin-only routes are separated from customer/operator routes.
- [ ] Role or permission model is documented before multi-customer use.
- [ ] Runtime-db-backed auth/session storage is enabled and migrated from any legacy `auth_store.json` state before rollout.
- [ ] Password reset, invite, and user deactivation path are documented or intentionally deferred.
- [ ] Admin session revocation and user activate/deactivate flows are verified.

## Runtime Storage

- [ ] `NERAIUM_RUNTIME_DIR` is configured for the target environment.
- [ ] Runtime database survives expected app restarts in the target environment.
- [ ] Upload job state persists across API/worker restarts.
- [ ] Evidence run state persists across API/worker restarts.
- [ ] Latest payloads persist or are intentionally ephemeral.
- [ ] Multi-task or multi-worker behavior is tested, or deployment is constrained to a known-safe topology.
- [ ] Migration path from SQLite/runtime files to shared production storage is documented.
- [ ] Runtime auth/session state is included in backup and restore checks.
- [ ] S3/shared upload state bucket is configured where required.

## Screenshots And Demo Assets

- [ ] README includes at least one current screenshot or short demo GIF.
- [ ] Mobile System Health captured.
- [ ] Mobile Data Connections captured.
- [ ] Mobile Evidence Trail captured.
- [ ] Mobile Historical Replay captured.
- [ ] Mobile Export Evidence captured.
- [ ] Tablet portrait captured.
- [ ] Tablet landscape captured.
- [ ] Desktop command surface captured.
- [ ] Upload success state captured.
- [ ] Upload failure state captured.
- [ ] Smoke output captured.
- [ ] Screenshots are current with the deployed UI.

## Security And Observability

- [ ] No secrets in UI.
- [ ] No secrets in logs.
- [ ] No secrets in metrics.
- [ ] No stack traces in production API responses.
- [ ] Request IDs or correlation IDs are available where expected.
- [ ] Upload, polling, SII processing, evidence export, 413, and 503 events are logged.
- [ ] Runtime worker failures are logged with actionable context.
- [ ] Audit events are created for important operator actions.
- [ ] Observability metrics are not publicly exposed without intended protection.

## CI And Validation

- [ ] CI workflow runs on push to `main`.
- [ ] CI workflow runs on pull requests.
- [ ] Backend tests run in CI.
- [ ] Frontend lint runs in CI.
- [ ] Frontend build runs in CI.
- [ ] Frontend unit tests run in CI.
- [ ] Dependency security scan runs in CI.
- [ ] Failed CI blocks merge or is treated as a release blocker.

## Deployment Workflow

- [ ] `gh workflow list --repo Neraium/Neraium-1.0` reviewed.
- [ ] CI workflow confirmed.
- [ ] Backend deployment workflow confirmed.
- [ ] Shared AWS bootstrap workflow confirmed.
- [ ] `NERAIUM_UPLOAD_STATE_BUCKET` and required repository variables confirmed.
- [ ] Required AWS secrets are present and rotated when needed.
- [ ] Rollback path documented.
- [ ] Post-deploy smoke order completed.

## Acceptance Decision

- [ ] Backend safe to deploy.
- [ ] Frontend safe to deploy.
- [ ] Operator flow safe to demonstrate.
- [ ] Remaining risks are documented with owner and next action.
