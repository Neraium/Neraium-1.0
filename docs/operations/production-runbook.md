# Production Deployment Runbook

This runbook covers the production architecture, deployment ownership, routing rules, failure modes, recovery procedures, and smoke tests for Neraium production.

Related references:

- `docs/AWS_DEPLOYMENT.md`
- `docs/DEPLOYMENT_RUNBOOK.md`
- `docs/OPERATIONS.md`
- `docs/CSV_UPLOAD_503_ROOT_CAUSE.md`

## Production Architecture

Production is split between static frontend hosting and containerized backend processing.

```text
Browser
  |
  | HTTPS
  v
app.neraium.com
  |
  +-- Static app origin: AWS Amplify Hosting, serving frontend/dist
  |
  +-- API path behavior, if same-origin API routing is enabled:
      /api/* -> CloudFront behavior -> backend origin -> ECS API service

Backend worker flow:
  ECS API service -> shared upload-state bucket -> ECS worker service
```

### Frontend

- The frontend is a Vite React single-page app in `frontend/`.
- Amplify builds from the repository using `amplify.yml`.
- Build steps are `cd frontend`, `npm install`, and `npm run build`.
- The published artifact directory is `frontend/dist`.
- Production bundles should not contain shared API secrets.
- API routing is configured through `frontend/src/config.js`.

The production frontend supports two API routing patterns:

1. Same-origin API routing, where production builds use relative `/api/*` paths and CloudFront routes those paths to ECS.
2. Direct backend routing, where Amplify sets `VITE_API_BASE_URL=https://<ecs-backend-url>` and the browser calls the ECS public HTTPS endpoint directly.

The preferred production posture is same-origin routing when CloudFront is configured correctly, because cookies and browser credentials stay on the production app origin.

### Backend

- The backend is a FastAPI service packaged by `backend/Dockerfile`.
- ECS runs two process roles from the same image:
  - `api`: handles HTTP requests and queues accepted uploads.
  - `worker`: claims queued uploads and performs analysis.
- The API and worker tasks must share the same `NERAIUM_UPLOAD_STATE_BUCKET`.
- The API task uses PostgreSQL from `NERAIUM_AUTH_DATABASE_URL` for production auth/session persistence.
- Runtime files live under `NERAIUM_RUNTIME_DIR=/mnt/neraium-runtime`.
- Health and readiness are separate:
  - `/api/health` is lightweight liveness.
  - `/api/ready` is deployment readiness.
  - `/api/ready?verbose=true` is operator diagnostics only.

## Amplify SPA Rewrite Rules

Amplify must serve the Vite app for client-side routes without stealing API requests.

Required SPA behavior:

- Requests for real static assets should resolve normally from `frontend/dist`.
- Unknown non-API browser routes should rewrite to `/index.html` with HTTP 200.
- `/api/*` must not be rewritten to `/index.html`.
- `/api/*` must either route to ECS through CloudFront or be avoided by setting `VITE_API_BASE_URL` to the ECS backend URL.

Recommended Amplify rewrite rule:

```text
Source address: </^[^.]+$|\.(?!(css|gif|ico|jpg|jpeg|js|png|svg|txt|webp|woff|woff2|json|map)$)([^.]+$)/>
Target address: /index.html
Type: 200 (Rewrite)
```

Operational checks:

```bash
curl -I https://app.neraium.com/
curl -I https://app.neraium.com/systems
curl -I https://app.neraium.com/assets/index.js
curl -i https://app.neraium.com/api/health
```

Expected outcomes:

- App routes return the SPA shell.
- Static assets return asset content with cache headers.
- `/api/health` returns FastAPI JSON when same-origin API routing is enabled.
- `/api/health` must not return the Amplify app shell, an S3 redirect, or generic CloudFront/ALB HTML.

## CloudFront Behavior

Use CloudFront only when production API requests are expected to share `app.neraium.com`.

Required behavior order:

1. `/api/*` behavior before the default static behavior.
2. Default behavior routes static frontend traffic to Amplify/static hosting.

Required `/api/*` behavior:

- Origin: backend ALB or ECS public HTTPS service.
- Viewer protocol policy: redirect HTTP to HTTPS or HTTPS only.
- Allowed methods: at least `GET`, `HEAD`, `OPTIONS`, and `POST`.
- Forward query strings.
- Forward cookies required for authenticated sessions.
- Forward required headers for CORS, request IDs, content type, authorization, and upload/session flows.
- Do not cache API responses by default.
- Align request-body limits with `NERAIUM_MAX_UPLOAD_SIZE_BYTES=262144000` before enabling upload flows through the distribution.

Failure indicators:

- `server: AmazonS3` on `https://app.neraium.com/api/health` means API traffic is hitting static hosting.
- `content-type: text/html` on API probes usually means CloudFront, ALB, or Amplify handled the request before FastAPI.
- `x-cache: Error from cloudfront` with `server: awselb/2.0` usually means the backend origin or target group is unhealthy.

## GitHub Actions Responsibilities

GitHub Actions owns validation, AWS bootstrap, backend image publishing, backend ECS rollout, and repository-level smoke coverage.

### CI

Workflow: `.github/workflows/ci.yml`

Runs on pushes to `main`, pull requests, and manual dispatch.

Responsibilities:

- Backend tests with Python 3.11.
- PostgreSQL integration tests.
- Frontend lint, build, and unit tests with Node 20.
- Backend dependency audit.
- Frontend production dependency audit.

### Backend Route Smoke Tests

Workflow: `.github/workflows/backend-smoke.yml`

Responsibilities:

- Run focused backend route smoke tests on pushes and pull requests.
- Detect broken route registration before deployment.

### Frontend Quality Gate

Workflow: `.github/workflows/frontend-smoke.yml`

Responsibilities:

- Install frontend dependencies.
- Install Playwright browsers.
- Run lint and build.
- Run Playwright setup and responsive smoke tests.
- Upload Playwright reports on failure.

### Bootstrap Production AWS

Workflow: `.github/workflows/bootstrap-production-aws.yml`

Responsibilities:

- Validate required repository variables and secrets.
- Run `scripts/bootstrap-production-aws.sh`.
- Ensure shared production bucket, task roles, and CloudWatch log groups exist.

Run manually when IAM, bucket, secret ARN, or log-group drift is suspected:

```bash
gh workflow run "Bootstrap Production AWS" --repo Neraium/Neraium-1.0 --ref main
gh run watch --repo Neraium/Neraium-1.0
```

### Deploy Backend To ECS

Workflow: `.github/workflows/deploy-backend.yml`

Runs automatically on pushes to `main` that change `backend/**`, the workflow file, or `scripts/bootstrap-production-aws.sh`. It can also be run manually.

Responsibilities:

- Configure AWS credentials.
- Login to ECR.
- Validate production settings.
- Run production bootstrap.
- Validate ECS cluster, services, and task-definition families.
- Build and push the backend image tagged with the GitHub commit SHA.
- Register new API and worker task definitions.
- Inject role-specific environment variables and secrets.
- Update both ECS services.
- Wait for services to stabilize.
- Verify worker startup and shared upload bucket configuration.
- Verify API bootstrap admin startup event where observable.

Manual deploy:

```bash
gh workflow run "Deploy Backend to ECS" --repo Neraium/Neraium-1.0 --ref main
gh run watch --repo Neraium/Neraium-1.0
```

## ECS Responsibilities

ECS owns backend process execution, task replacement, service stabilization, task-definition revisions, and CloudWatch logs.

Production service names:

```text
Cluster: neraium-prod-cluster
API service: neraium-prod-api-service
Worker service: neraium-prod-worker-service
API task family: neraium-prod-api
Worker task family: neraium-prod-worker
API log group: /ecs/neraium-prod-api
Worker log group: /ecs/neraium-prod-worker
Region: us-east-2
```

Required API role settings:

```text
NERAIUM_PROCESS_ROLE=api
APP_ENV=prod
NERAIUM_UPLOAD_STATE_BUCKET=<shared-s3-bucket>
NERAIUM_RUNTIME_DIR=/mnt/neraium-runtime
CORS_ORIGINS=https://app.neraium.com
NERAIUM_AUTH_DATABASE_URL=<secret-injected-postgres-dsn>
NERAIUM_API_TOKEN=<secret-injected-service-token>
```

Required worker role settings:

```text
NERAIUM_PROCESS_ROLE=worker
APP_ENV=prod
NERAIUM_UPLOAD_STATE_BUCKET=<shared-s3-bucket>
NERAIUM_RUNTIME_DIR=/mnt/neraium-runtime
CORS_ORIGINS=https://app.neraium.com
```

Operational rules:

- Do not share a SQLite runtime database between API and worker tasks.
- Do not put secrets in plain task-definition environment arrays.
- Preserve role-specific durable mounts if runtime history must survive task replacement.
- Keep previous task-definition revisions available for rollback.
- Use `/api/health` for load-balancer liveness.
- Use `/api/ready` for deployment verification.

Useful AWS checks:

```bash
aws ecs describe-services \
  --cluster neraium-prod-cluster \
  --services neraium-prod-api-service neraium-prod-worker-service \
  --region us-east-2

aws ecs list-tasks \
  --cluster neraium-prod-cluster \
  --service-name neraium-prod-api-service \
  --desired-status RUNNING \
  --region us-east-2

aws logs filter-log-events \
  --log-group-name /ecs/neraium-prod-api \
  --filter-pattern 'readiness_dependency_failed' \
  --region us-east-2
```

## Common Failure Modes

### API Requests Return HTML

Symptoms:

- API probes return `content-type: text/html`.
- Frontend reports that the analysis service could not be reached.
- API response body contains a static app shell, Amplify page, CloudFront error page, or ALB 503 page.

Likely causes:

- Amplify SPA rewrite is catching `/api/*`.
- CloudFront `/api/*` behavior is missing or ordered after the default behavior.
- Backend origin is unhealthy.
- Direct backend routing is not configured and same-origin routing is incomplete.

Recovery:

1. Run `curl -i https://app.neraium.com/api/health`.
2. If the response is the app shell or S3 redirect, fix Amplify/CloudFront routing.
3. If the response is ALB or CloudFront 503 HTML, inspect ECS service health and target group health.
4. Confirm direct backend health if the ECS backend URL is known.
5. Rerun production smoke after routing is fixed.

### CloudFront Or ALB Returns 503

Symptoms:

- `x-cache: Error from cloudfront`.
- `server: awselb/2.0`.
- `503 Service Temporarily Unavailable`.
- ECS API service has desired count above zero but running count is zero or targets are unhealthy.

Likely causes:

- API task fails startup configuration.
- ALB health check times out.
- Runtime volume, auth database, or required secrets are invalid.
- Health check path is too heavy or misconfigured.

Recovery:

1. Check ECS service events and task stop reasons.
2. Check `/ecs/neraium-prod-api` logs for startup failures.
3. Confirm health check path is `/api/health`.
4. Confirm `/api/ready` is not being used as a high-frequency liveness probe.
5. Fix the failing environment variable, secret, IAM permission, or runtime mount.
6. Rerun the backend deploy workflow or force a new ECS deployment.

### Upload Accepted But Never Completes

Symptoms:

- `POST /api/data/upload` returns a `job_id`.
- Polling `/api/data/upload-status/<job_id>` remains queued or pending.
- No result appears in latest upload.

Likely causes:

- API and worker do not share the same `NERAIUM_UPLOAD_STATE_BUCKET`.
- Worker task is not running.
- Worker IAM role cannot read/write shared upload state.
- Worker exits during startup.
- Queue is saturated.

Recovery:

1. Compare API and worker task definitions for `NERAIUM_UPLOAD_STATE_BUCKET`.
2. Confirm the worker service has running tasks.
3. Search worker logs for `upload_worker_started`, `job_claimed`, and processing failures.
4. Search API logs for `upload_job_accepted` and `upload_queue_lifecycle_event`.
5. Run `Bootstrap Production AWS` if bucket or role drift is suspected.
6. Rerun backend deployment after correcting configuration.

### CORS Or Authentication Failures

Symptoms:

- Browser preflight fails.
- Login succeeds in direct API probes but frontend calls fail.
- API returns 401/403 unexpectedly.

Likely causes:

- `CORS_ORIGINS` does not include the production frontend origin.
- CloudFront is not forwarding cookies or authorization/session headers.
- The browser is calling a different backend origin than expected.
- Session store secret or PostgreSQL configuration is invalid.

Recovery:

1. Confirm frontend route mode in the browser and built API target.
2. Confirm `CORS_ORIGINS=https://app.neraium.com` in the API task definition.
3. Confirm CloudFront forwards required cookies and headers for `/api/*`.
4. Check `/api/auth/me` and protected API routes from the browser.
5. Check API logs for authentication-store startup failures or denied routes.

### Amplify Deploys Old Or Misconfigured Frontend

Symptoms:

- UI changes do not appear after pushing `main`.
- Frontend calls stale or unexpected API hosts.
- Static routes work but upload flows fail after backend changes.

Likely causes:

- Amplify build did not run or failed.
- Amplify app root or artifact directory is wrong.
- `VITE_API_BASE_URL` is stale.
- Browser or edge cache still serves old assets.

Recovery:

1. Inspect the Amplify deployment for the latest commit SHA.
2. Confirm `amplify.yml` still publishes `frontend/dist`.
3. Confirm environment variables in Amplify.
4. Redeploy the Amplify branch.
5. Invalidate or wait out edge/browser cache if hashed assets are not advancing.
6. Run the frontend smoke checks against production.

### Backend Deploy Workflow Fails

Symptoms:

- GitHub Actions deploy stops before ECS update.
- Workflow fails validating inputs, task families, services, or secret ARNs.

Likely causes:

- Required repository secrets or variables are absent.
- ECS cluster, service, or task family was renamed or deleted.
- Bootstrap resources drifted.
- AWS credentials cannot access the required resources.

Recovery:

1. Read the first failing step in the Actions log.
2. Repair missing repo secrets/variables or AWS resources.
3. Run `Bootstrap Production AWS`.
4. Rerun `Deploy Backend to ECS`.

## Recovery Procedures

### Roll Back Frontend

Use this when backend health is good but the browser experience is broken.

1. Revert or redeploy the last known good Amplify build from the Amplify console.
2. Confirm the deployed commit and environment variables.
3. Confirm SPA routes and API routes separately.
4. Run frontend smoke checks and a small upload from the live UI.

### Roll Back Backend

Use this when `/api/health`, `/api/ready`, uploads, auth, or worker processing regressed after backend deployment.

1. Identify the previous healthy API and worker task-definition revisions.
2. Update both ECS services to the previous matching revisions.
3. Wait for services to stabilize.
4. Confirm API and worker tasks are running.
5. Run production smoke.
6. Preserve failed deploy logs, task stop reasons, task-definition ARNs, and smoke output.

Example rollback shape:

```bash
aws ecs update-service \
  --cluster neraium-prod-cluster \
  --service neraium-prod-api-service \
  --task-definition neraium-prod-api:<previous-api-revision> \
  --region us-east-2

aws ecs update-service \
  --cluster neraium-prod-cluster \
  --service neraium-prod-worker-service \
  --task-definition neraium-prod-worker:<previous-worker-revision> \
  --region us-east-2

aws ecs wait services-stable \
  --cluster neraium-prod-cluster \
  --services neraium-prod-api-service neraium-prod-worker-service \
  --region us-east-2
```

### Repair Shared AWS Resources

Use this when bucket, IAM, log group, or secret ARN drift is suspected.

```bash
gh workflow run "Bootstrap Production AWS" --repo Neraium/Neraium-1.0 --ref main
gh run watch --repo Neraium/Neraium-1.0
```

Then rerun the backend deployment if task definitions need updated injected values.

### Recover From Queue Or Worker Drift

1. Confirm API and worker services are on compatible task-definition revisions.
2. Confirm both roles use the same upload-state bucket and prefix.
3. Confirm worker logs show startup and claims.
4. Restart the worker service with a forced deployment if it is wedged but configuration is correct.
5. Run the production smoke upload and verify `latest-upload` advances.

## Post-Deployment Smoke Tests

Run smoke tests after every production deployment and after any routing change.

### GitHub And Platform Checks

```bash
gh run list --repo Neraium/Neraium-1.0 --limit 10
gh run watch --repo Neraium/Neraium-1.0
```

Confirm:

- CI passed for the deployed commit.
- Backend deploy passed if backend files changed.
- Amplify deployed the intended commit if frontend files changed.
- ECS API and worker services are stable.

### API Smoke

Same-origin routing target:

```bash
BASE_URL=https://app.neraium.com node scripts/smoke-production.js
```

Direct backend target:

```bash
BASE_URL=https://<ecs-backend-url> node scripts/smoke-production.js
```

If metrics requires a service token:

```bash
BASE_URL=https://app.neraium.com NERAIUM_API_TOKEN="$NERAIUM_API_TOKEN" node scripts/smoke-production.js
```

The smoke script must:

- Probe `/api/health`.
- Probe `/api/ready`.
- Probe `/api/intelligence/runner-status`.
- Probe `/api/observability/metrics` when allowed.
- Upload a small CSV.
- Poll the upload to `COMPLETE`.
- Confirm the SII runner was used.
- Confirm `latest-upload` and runner state advanced.

### Manual Route Smoke

```bash
curl -i https://app.neraium.com/api/health
curl -i https://app.neraium.com/api/ready
curl -i https://app.neraium.com/api/intelligence/runner-status
curl -I https://app.neraium.com/
curl -I https://app.neraium.com/systems
```

Expected:

- API routes return JSON from FastAPI.
- SPA routes return HTML from the frontend.
- No API route returns static app HTML, S3 redirects, or generic CloudFront/ALB HTML.

### Browser Smoke

Use the live production frontend:

1. Open `https://app.neraium.com`.
2. Sign in as a production operator or admin.
3. Confirm the main workspace loads without stale-session errors.
4. Upload a small known-good CSV.
5. Confirm upload progress advances through queued, processing, and complete states.
6. Confirm the result page opens.
7. Confirm evidence, replay, and latest upload state correspond to the smoke file.
8. Refresh the browser and confirm the latest upload view still resolves.
9. Check mobile viewport behavior for the upload and result surfaces.

### Log Smoke

Search production logs for deployment and upload lifecycle signals:

```bash
aws logs filter-log-events \
  --log-group-name /ecs/neraium-prod-api \
  --filter-pattern 'upload_job_accepted' \
  --region us-east-2

aws logs filter-log-events \
  --log-group-name /ecs/neraium-prod-worker \
  --filter-pattern 'sii_state_published' \
  --region us-east-2
```

Expected:

- API logs show accepted upload and status polling.
- Worker logs show job claim, processing, evidence persistence, and SII state publication.
- No new `readiness_dependency_failed`, startup failure, or repeated unhandled exception appears for the deployed build.

## Deployment Record

For each production deployment, preserve:

- GitHub commit SHA.
- GitHub Actions run IDs.
- Amplify deployment ID and commit.
- API and worker task-definition ARNs.
- Smoke-test output.
- Any rollback or remediation commands.
- Screenshots for operator-visible changes.
