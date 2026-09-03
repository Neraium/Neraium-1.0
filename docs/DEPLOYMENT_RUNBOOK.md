# Deployment Runbook

See `docs/OPERATIONS.md` for the production configuration contract, log schema, probe semantics, monitoring guidance, resource ownership, and troubleshooting procedures.

This runbook covers the production deployment and verification sequence for Neraium.

## Preflight

```bash
git status --short
npm --prefix frontend run build
python -m pytest tests/test_health.py tests/test_config.py tests/test_logging.py tests/test_operational_lifecycle.py tests/test_data_upload.py -q
BASE_URL=http://127.0.0.1:8010 node scripts/smoke-production.js
python scripts/pilot_rehearsal_check.py
```

For production smoke tests:

```bash
BASE_URL=https://app.neraium.com node scripts/smoke-production.js
BASE_URL=https://app.neraium.com python scripts/pilot_rehearsal_check.py
```

The production smoke script now performs the basic API probes plus a tiny telemetry upload that must reach `COMPLETE`, use the SII runner, and advance the visible runtime state.
The pilot rehearsal script adds deterministic bad-telemetry fixtures, captures endpoint/upload outcomes, and writes an evidence report under `output/pilot-rehearsal/`.

## CSV Throughput Tuning (Pilot)

CSV validation scans the full uploaded file while downstream analysis uses the configured bounded sample (100,000 rows by default). Production supports multipart uploads through 250 MiB and presigned browser-to-S3 CSV uploads through 512 MiB. Keep the S3 upload CORS rule, 4 GiB worker memory, 40 GiB worker ephemeral storage, queue depth, and timeouts aligned with those limits.

If metrics requires auth for CLI smoke checks:

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

Bootstrap or repair the shared AWS production resources with:

```bash
gh workflow run "Bootstrap Production AWS" --repo Neraium/Neraium-1.0 --ref main
gh run watch --repo Neraium/Neraium-1.0
```

Required repository variables before running either workflow (the bootstrap password itself remains stored in Secrets Manager):

```text
secret: NERAIUM_UPLOAD_STATE_BUCKET=<shared-s3-bucket>
NERAIUM_APP_TASK_ROLE_NAME=neraium-prod-task-app-role
NERAIUM_API_TOKEN_SECRET_ARN=arn:aws:secretsmanager:us-east-2:<account-id>:secret:<secret-name>
NERAIUM_AUTH_DATABASE_URL_SECRET_ARN=arn:aws:secretsmanager:us-east-2:<account-id>:secret:<legacy-postgres-dsn-secret>  # rollback compatibility; active tasks use the discovered RDS managed secret
NERAIUM_TELEMETRY_DATABASE_URL_SECRET_ARN=arn:aws:secretsmanager:us-east-2:<account-id>:secret:<telemetry-application-dsn-secret>
NERAIUM_TELEMETRY_MIGRATION_DATABASE_URL_SECRET_ARN=arn:aws:secretsmanager:us-east-2:<account-id>:secret:<telemetry-migration-dsn-secret>
NERAIUM_BOOTSTRAP_ADMIN_EMAIL=<pilot-admin-email>
NERAIUM_BOOTSTRAP_ADMIN_PASSWORD_SECRET_ARN=arn:aws:secretsmanager:us-east-2:<account-id>:secret:<bootstrap-admin-password-secret>
NERAIUM_BOOTSTRAP_ADMIN_RESET_PASSWORD=false  # set true only for an intentional password reset
```

The workflows discover the production RDS endpoint, rotating master secret ARN, and KMS key directly from `neraium-prod-postgres`; do not copy the rotating password into a separate DSN secret. The active production path is GitHub Actions plus AWS CLI. Terraform is deprecated and should not be used to register or update ECS task definitions. The backend deploy workflow expects the ECS cluster, API service, worker service, and both task-definition families to already exist, and now fails early if they do not.

Production telemetry uses the same supported RDS instance and `postgres` database through its additive `telemetry` schema, but it does not use the rotating master secret at runtime. Before deployment, create the two referenced DSN secrets with separate least-privilege PostgreSQL identities: a temporary migration identity with bounded DDL authority and an API/worker identity with only the required `telemetry` schema DML. Both DSNs must require TLS; prefer `sslmode=verify-full` when the container trust store and RDS hostname verification have been validated. The deploy runs migrations 002, 003, 004, and the current readiness-required 005 through a one-off ECS task before updating either service.

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
3. `GET /api/intelligence/runner-status`.
4. `GET /api/observability/metrics` with auth if required.
5. Upload a small CSV and confirm the queued job reaches `COMPLETE`.
6. Verify `latest-upload` and runner state advanced to the smoke file.
7. Test Connection.
8. Poll Once.
9. Start Polling, confirm state, then stop polling.
10. Evidence Trail.
11. Historical Replay.
12. Export Evidence.
13. Validate a synthetic 409.5 MiB file identity selects the presigned path without allocating/uploading that fixture.
14. Confirm the S3 CORS preflight permits `PUT` and exposes `ETag`.
15. 413 oversize upload guardrail above 512 MiB.
16. 503 queue saturation guardrail in staging or documented safe local test.

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
- `readiness_dependency_failed` and readiness degradation
- `evidence_run_persisted`
- `sii_state_published`
- `*_shutdown_timeout`

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
