# Deployment Runbook

This runbook covers the production deployment and verification sequence for Neraium.

## Preflight

```bash
git status --short
npm --prefix frontend run build
python -m pytest tests/test_health.py tests/test_data_upload.py -q
node scripts/smoke-production.js
```

For production smoke tests:

```bash
BASE_URL=https://app.neraium.com node scripts/smoke-production.js
```

If metrics requires auth:

```bash
BASE_URL=https://app.neraium.com NERAIUM_API_TOKEN=$NERAIUM_API_TOKEN node scripts/smoke-production.js
```

## GitHub Workflow Discovery

```bash
gh workflow list --repo Neraium/Neraium-1.0
```

The backend deployment command requested for this repo is:

```bash
gh workflow run "Deploy Backend to ECS" --repo Neraium/Neraium-1.0 --ref main
```

Watch the active run:

```bash
gh run watch --repo Neraium/Neraium-1.0
```

If the Terraform workflow does not appear in `gh workflow list`, treat Terraform deployment as not configured in GitHub Actions and use the documented infrastructure process for this repository before changing infrastructure.

This repository currently includes `.github/workflows/infra-apply.yml` with the workflow name `Apply Infrastructure (Terraform)`.

Run Terraform plan only:

```bash
gh workflow run "Apply Infrastructure (Terraform)" --repo Neraium/Neraium-1.0 --ref main -f action=plan
gh run watch --repo Neraium/Neraium-1.0
```

Run Terraform apply only after plan review and approval:

```bash
gh workflow run "Apply Infrastructure (Terraform)" --repo Neraium/Neraium-1.0 --ref main -f action=apply
gh run watch --repo Neraium/Neraium-1.0
```

## Recommended Deployment Order

1. Confirm frontend build and backend tests locally.
2. Confirm guardrail tests locally or in staging.
3. Deploy backend first so SII, health, readiness, upload, polling, evidence, replay, and export contracts are current.
4. Run backend smoke checks against production.
5. Deploy frontend after backend smoke passes.
6. Run full operator flow on mobile, tablet, and desktop.
7. Capture screenshots required by the production operator checklist.

## Smoke Test Order

1. `GET /api/health`.
2. `GET /api/ready`.
3. `GET /api/observability/metrics` with auth if required.
4. Upload a small CSV.
5. Test Connection.
6. Poll Once.
7. Start Polling, confirm state, then stop polling.
8. Evidence Trail.
9. Historical Replay.
10. Export Evidence.
11. 413 oversize upload guardrail.
12. 503 queue saturation guardrail in staging or documented safe local test.

## Watch And Logs

Use the deployment platform logs plus GitHub run watch:

```bash
gh run watch --repo Neraium/Neraium-1.0
```

Check backend logs for:

- `upload_job_accepted`
- `upload_rejected_oversize`
- SII processing success or failure
- polling start, stop, and poll result events
- evidence export events
- readiness degradation

## Rerun

```bash
gh run list --repo Neraium/Neraium-1.0 --limit 10
gh run rerun RUN_ID --repo Neraium/Neraium-1.0
gh run watch --repo Neraium/Neraium-1.0
```

## Rollback Notes

- Prefer rolling back the last frontend deployment first if the backend smoke endpoints remain healthy.
- Prefer rolling back backend if `/api/health` or `/api/ready` fails after deployment.
- Do not roll forward with a broken upload, polling, Evidence Trail, Replay, or Export flow.
- Preserve logs, run IDs, smoke output, and screenshots for post-deploy review.
