# Production Acceptance Checklist

Use this as the final go or no-go checklist for investor demos, pilot deployments, and enterprise/operator use.

## Smoke Endpoints

- [ ] `GET /api/health` returns success.
- [ ] `GET /api/ready` returns success.
- [ ] `GET /api/observability/metrics` returns metrics or documented auth warning.
- [ ] Smoke script detects no HTML error pages.

## Operator Flow

- [ ] Upload CSV passes.
- [ ] API config flow passes.
- [ ] Test Connection passes.
- [ ] Poll Once passes.
- [ ] Start Polling passes and duplicate polling is prevented.
- [ ] Stop Polling works cleanly.
- [ ] Evidence Trail opens and explains what changed.
- [ ] Historical Replay opens and shows available evidence history.
- [ ] Export Evidence succeeds and contains traceable metadata.

## Guardrails

- [ ] Oversize upload returns 413.
- [ ] Queue saturation returns 503 or is documented as safely tested only in staging/local.
- [ ] Rejected uploads do not create fake completed evidence.
- [ ] Recovery after guardrail rejection is confirmed.

## SII Source Of Truth

- [ ] No production dashboard output is fabricated in the frontend.
- [ ] Missing SII output shows "Awaiting SII analysis".
- [ ] Operational conclusions are evidence-linked.
- [ ] Runway or projected time-to-failure is shown only when provided by backend/SII output.
- [ ] Sample mode is explicitly labeled and never silently replaces production output.

## Screenshots

- [ ] Mobile System Health captured.
- [ ] Mobile Data Connections captured.
- [ ] Mobile Evidence Trail captured.
- [ ] Mobile Historical Replay captured.
- [ ] Mobile Export Evidence captured.
- [ ] Tablet portrait captured.
- [ ] Tablet landscape captured.
- [ ] Desktop command surface captured.
- [ ] Smoke output captured.

## Security And Observability

- [ ] No secrets in UI.
- [ ] No secrets in logs.
- [ ] No secrets in metrics.
- [ ] No stack traces in production API responses.
- [ ] Request IDs or correlation IDs are available where expected.
- [ ] Upload, polling, SII processing, evidence export, 413, and 503 events are logged.

## Deployment Workflow

- [ ] `gh workflow list --repo Neraium/Neraium-1.0` reviewed.
- [ ] Backend deployment workflow confirmed.
- [ ] Shared AWS bootstrap workflow confirmed.
- [ ] `NERAIUM_UPLOAD_STATE_BUCKET` and `NERAIUM_APP_TASK_ROLE_NAME` repository variables confirmed.
- [ ] Rollback path documented.
- [ ] Post-deploy smoke order completed.

## Acceptance Decision

- [ ] Backend safe to deploy.
- [ ] Frontend safe to deploy.
- [ ] Pilot flow safe to demonstrate.
- [ ] Remaining risks are documented with owner and next action.
