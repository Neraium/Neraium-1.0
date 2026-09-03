# AWS Deployment Preparation

This document captures the active AWS deployment path for Neraium-1.0. Production bootstrap and ECS deployment are handled by a checked-in AWS CLI script plus GitHub Actions. Terraform is inactive and not the production source of truth.

The checked-in production bootstrap/deploy workflow now accepts pre-provisioned telemetry application and migration DSN secret ARNs, grants the ECS execution role access to those exact secrets, applies migrations 002-005 in a one-off task, verifies the resulting schema through the application DSN in that same task, and injects the application DSN secret into both API and worker revisions. It does **not** create the database identities or secrets, grant PostgreSQL privileges, change RDS networking, enable controlled connector egress, register historian templates, or provision telemetry-specific alarms. The [production telemetry section](#production-telemetry-connections-separate-approval-required) remains a required handoff, not a claim about deployed AWS state.

## Targets

- Backend: Amazon ECS Express Mode / ECS Fargate
- Backend container image registry: Amazon ECR
- Frontend: AWS Amplify Hosting
- Production backend container port: `8080`
- Public load balancer listeners: `80` and `443`, forwarding to the `8080` container target
- Local backend port: `8010`
- Local frontend port: `3010`

## Backend: ECS Express Mode / ECS Fargate

The backend remains a FastAPI Docker container. `backend/Dockerfile` runs:

```text
python -m app.entrypoint
```

Backend deployment notes:

1. Build the backend Docker image from the repository root:

```powershell
docker build -t neraium-backend:local .\\backend
```

2. Create an Amazon ECR repository for the backend image.
3. Tag and push the backend image to Amazon ECR.
4. Create an Amazon ECS Express Mode service from the ECR image.
5. Configure the container port as `8080`.
6. Configure the health check path as `/api/health`.
7. Confirm the ECS-generated public HTTPS URL returns a healthy response:

```text
https://<ecs-backend-url>/api/health
```

Required backend environment variables:

```text
APP_ENV=production
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8080
CORS_ORIGINS=https://<amplify-frontend-domain>
NERAIUM_RUNTIME_DIR=/mnt/neraium-runtime
NERAIUM_UPLOAD_CHUNK_SIZE_ROWS=10000
NERAIUM_MAX_UPLOAD_SIZE_BYTES=262144000
NERAIUM_MAX_PENDING_UPLOAD_JOBS=50
```

Production split-role backend behavior does require a shared upload-state bucket and task-role access for API/worker queue coordination. Set these on both ECS task definitions:

```text
NERAIUM_UPLOAD_STATE_BUCKET=<shared-s3-bucket>
NERAIUM_PROCESS_ROLE=api|worker
# API task only; the workflow discovers these values from the managed RDS instance.
NERAIUM_AUTH_DATABASE_SECRET_ARN=<rds-managed-json-secret-arn>
NERAIUM_AUTH_DATABASE_HOST=<rds-endpoint>
NERAIUM_AUTH_DATABASE_PORT=5432
NERAIUM_AUTH_DATABASE_NAME=postgres
NERAIUM_AUTH_DATABASE_SSLMODE=require
NERAIUM_EMPLOYEE_ONBOARDING_CODE=<inject from Secrets Manager into the API task only>
NERAIUM_EMPLOYEE_ONBOARDING_WORKSPACE_ID=ws-<active-production-facility-uuid>
```

The ECS deployment workflow registers both task definitions directly with AWS CLI. It expects the production ECS cluster, API service, worker service, and both task-definition families to already exist, validates those resources before image build, and fails fast if any are missing or inactive. New revisions pin the entrypoint, process role, CORS, upload limits, JSON logging, build SHA, runtime path, shared-state bucket, log group, and secret references.

`.aws/task-definition.json` is a legacy reference artifact and is not registered by the active deployment workflow. The live task families are the deployment baseline. Their volume and mount definitions are preserved: each role must already have its own durable writable volume mounted at `/mnt/neraium-runtime` if runtime history must survive task replacement. Do not share a SQLite runtime database between API and worker tasks; use distinct per-role volumes or EFS access points.

```text
command=["python","-m","app.entrypoint"]
awslogs group=/ecs/neraium-prod-api or /ecs/neraium-prod-worker
```

Upload path audit: multipart requests through the API are capped at 250 MiB (`NERAIUM_MAX_UPLOAD_SIZE_BYTES=262144000`). CSVs from 250 MiB through 512 MiB use an authenticated upload session, direct browser-to-S3 presigned `PUT`, server-side object verification, and canonical job creation. The deployment sets `NERAIUM_MAX_LARGE_UPLOAD_SIZE_BYTES=536870912`, configures bucket CORS/ETag exposure and orphan cleanup, and gives the worker 1 vCPU, 4 GiB memory, and 40 GiB ephemeral storage. No NGINX reverse proxy is deployed in this stack.

The API task also receives `NERAIUM_BOOTSTRAP_ADMIN_EMAIL` as an environment variable, `NERAIUM_BOOTSTRAP_ADMIN_RESET_PASSWORD` from the repository variable (default `false`), and `NERAIUM_BOOTSTRAP_ADMIN_PASSWORD` from the Secrets Manager secret referenced by `NERAIUM_BOOTSTRAP_ADMIN_PASSWORD_SECRET_ARN`. The API startup normalizes the email, creates a missing administrator, and repairs an existing account's active/admin state. It resets the password only when the reset flag is `true`; otherwise the existing password is preserved. Neither bootstrap administrator value nor the reset flag is injected into the worker task. Startup emits only the non-secret result events `bootstrap_admin_created`, `bootstrap_admin_already_exists`, `bootstrap_admin_updated`, `bootstrap_admin_skipped_missing_configuration`, or `bootstrap_admin_failed`.

For split-role production ECS, do not rely on `NERAIUM_RUNTIME_DIR` for cross-task queue state. The queue and latest-upload state are shared through `NERAIUM_UPLOAD_STATE_BUCKET`.
Evidence Package Correlation source and relationship sidecars use that same
shared bucket. Both API and worker task roles therefore need the existing
read/write/list permissions for the configured upload-state prefix; no new
bucket or environment variable is introduced.

## Frontend: AWS Amplify Hosting

The frontend remains a static Vite React app hosted by AWS Amplify Hosting.

Production builds are created with:

```powershell
cd frontend
npm install
npm run build
```

Amplify setup notes:

1. Connect Amplify Hosting to the GitHub repository.
2. Set the app root to `frontend` if Amplify is connected to the repository root.
3. Use `npm install` for dependency installation.
4. Use `npm run build` as the build command.
5. Publish the `frontend/dist` directory.
6. Set `VITE_API_BASE_URL` to the ECS-generated public HTTPS backend URL.

Required frontend environment variable (direct backend routing pattern):

```text
VITE_API_BASE_URL=https://<ecs-backend-url>
```

Important routing note:

- `app.neraium.com/api/*` must reach the backend origin, not Amplify/S3 static hosting.
- If `curl -i https://app.neraium.com/api/health` returns `301` with `server: AmazonS3`, API traffic is misrouted.

Two valid production patterns:

1. Direct backend URL from frontend build
- Set `VITE_API_BASE_URL=https://<ecs-backend-url>` in Amplify environment variables.
- Frontend calls backend directly for all `/api/*` requests.

2. CloudFront path behavior for same-domain API
- Keep frontend on static origin (Amplify/S3).
- Add CloudFront behavior for `/api/*` with backend origin (ALB/ECS service).
- Forward query strings, required headers, and cookies for authenticated requests.
- Ensure all API methods are allowed for the backend behavior (`GET`, `HEAD`, `OPTIONS`, `POST`, `PUT`, `PATCH`, and `DELETE`). The presigned object upload is a separate S3 `PUT` governed by bucket CORS.

Required API routes to backend origin:

- `/api/data-connections*`
- `/api/findings*`
- `/api/evidence*`
- `/api/data/upload`
- `/api/data/upload-session`
- `/api/data/upload-session/*/complete`
- `/api/data/upload-status/*`
- `/api/data/upload-stream/*`

The local frontend default remains `http://127.0.0.1:8010` when `VITE_API_BASE_URL` is not set.

## Production telemetry connections: separate approval required

The application-side contract is documented in [Production Telemetry Connections](TELEMETRY_CONNECTIONS.md). No telemetry AWS, IAM, database, network, or production change was performed as part of the implementation campaign.

### Pre-deploy inventory

Before changing AWS, an authorized operator must record and verify, without pasting secret values:

- the target AWS account, region, ECS cluster, API service/task family, worker service/task family, and current rollback revisions;
- the shared PostgreSQL/RDS endpoint and database that will own the additive `telemetry` schema;
- the API and worker task roles and the migration role;
- the KMS key used by connection secrets, if not the AWS managed Secrets Manager key;
- the actual API/worker VPC subnets, security groups, DNS resolver path, NAT/egress proxy/firewall, and approved customer source destinations;
- CloudWatch log groups, metric filters/alarms, and worker desired count;
- whether credentials will use dynamic API writes or a server-owned pre-provisioned binding workflow;
- whether any reviewed historian template/executor and private network profile actually exist. The default application registry is empty.

Do not infer these values from examples in this repository. Compare them with the live task definitions and approved infrastructure inventory before proceeding.

### PostgreSQL prerequisites

Use a shared PostgreSQL authority on a repository-supported version, reachable from both API and worker tasks. Production `NERAIUM_TELEMETRY_DATABASE_URL` validation requires TLS (`sslmode=require`, `verify-ca`, or `verify-full`; prefer `verify-full` with an approved CA). Store the DSN in Secrets Manager/SSM and inject it through the ECS task-definition `secrets` array. Do not put it in the task-definition `environment` array or GitHub logs.

Use separate identities where the deployment supports them:

- migration identity: the bounded DDL permissions needed to create/alter the `telemetry` schema and its objects;
- application API/worker identity or identities: connect plus only the schema/table/sequence DML needed by the repository, with no schema drop/owner/superuser rights.

The exact forward-only migration and verifier commands are in [Database migrations](database-migrations.md#production-telemetry-schema). Apply 002, 003, 004, then the current readiness-required 005 before any task receives `NERAIUM_TELEMETRY_DATABASE_URL`. Application startup verifies but never applies migrations.

### Secrets Manager and IAM prerequisites

Connection secrets use the namespace:

```text
neraium/<environment>/telemetry-connections/*
```

They must carry ownership tags for `neraium:managed-by`, `neraium:resource-scope-id`, and `neraium:connection-id`. Scope resource permissions to the environment namespace and constrain create/tag behavior with reviewed tag conditions. Do not grant `ListSecrets`, `DeleteSecret`, broad wildcard secret access, or access to another environment.

Required actions depend on the approved credential model:

| Principal | Pre-provisioned binding | Dynamic credential write |
|---|---|---|
| API task role | `secretsmanager:DescribeSecret`, `secretsmanager:GetSecretValue` for validation/discovery | Add scoped `CreateSecret` and `UpdateSecret`; retain scoped describe/get |
| Worker task role | `secretsmanager:DescribeSecret`, `secretsmanager:GetSecretValue` | Same read-only actions; worker does not create/update secrets |
| Approved operations/migration principal | Provision/tag/bind according to the reviewed runbook only | No standing application access required |

Add `kms:Decrypt` only for the exact customer-managed key when required. Secret creation with a customer-managed key may need separately reviewed KMS encrypt/data-key permissions. Do not add KMS or IAM permissions by assumption.

Keep `NERAIUM_TELEMETRY_DYNAMIC_SECRET_WRITES=false` unless the dynamic-write policy has been reviewed and deployed. If it remains false, customer credential submission is intentionally unavailable until a server-owned pre-provisioned binding operation exists; the browser cannot submit an ARN/reference.

### Egress and provider prerequisites

The HTTPS adapter performs application-level SSRF checks and pins authorized DNS answers to the socket. Production still requires an independent controlled-egress boundary. Before setting `NERAIUM_TELEMETRY_CONTROLLED_EGRESS_ENABLED=true`:

1. route connector HTTPS through an approved egress firewall/proxy/NAT policy;
2. deny loopback, RFC1918, link-local, metadata, multicast, reserved, and other non-public destinations independently of application code;
3. restrict outbound TCP to 443 and approved destination policy where operationally possible;
4. ensure environment proxy variables cannot bypass the policy (the connector itself uses `trust_env=false`);
5. verify DNS resolution and direct-address TLS/SNI behavior from the worker task network;
6. define logging that records safe outcome/code/latency without full URLs, query values, headers, credentials, or payloads.

Private historian/customer sources require a separately approved network architecture and a registered `ServerHistorianTemplate`/executor. Do not open generic private egress and do not expose SQL, DSN, path, host, port, or query templates to the browser.

### Task-definition configuration

After schema, IAM, Secrets Manager, and egress approval, inject the following into both API and worker revisions as appropriate:

```text
# secret injection on API and worker
NERAIUM_TELEMETRY_DATABASE_URL=<telemetry PostgreSQL DSN secret>

# non-secret environment on API and worker
NERAIUM_TELEMETRY_SECRET_REGION=<approved AWS region>
NERAIUM_TELEMETRY_CONTROLLED_EGRESS_ENABLED=true
NERAIUM_TELEMETRY_LEGACY_COMPAT=false
NERAIUM_TELEMETRY_SCHEDULER_POLL_INTERVAL_SECONDS=2
NERAIUM_TELEMETRY_SCHEDULER_LEASE_SECONDS=120
NERAIUM_TELEMETRY_WORKER_HEARTBEAT_INTERVAL_SECONDS=30

# only if dynamic secret IAM was separately approved
NERAIUM_TELEMETRY_DYNAMIC_SECRET_WRITES=true
```

The timing values shown are application defaults, not sizing evidence. Change them only from measured source/API latency and lease behavior. Keep `NERAIUM_START_DATA_POLLER=false`. The existing worker role must have `NERAIUM_START_BACKGROUND_WORKERS=true` (or its role default), a nonzero desired count, and enough stop grace to finish or safely expire a bounded page. Do not run a separate frontend poller or the legacy API-thread data poller.

Update the active GitHub deployment workflow or task-definition source of truth to preserve these settings in later revisions. A one-off console edit that the next workflow registration removes is not a valid deployment.

### Telemetry monitoring prerequisites

Extend CloudWatch monitoring before enablement. At minimum capture/alert on:

- telemetry worker heartbeat absent/degraded and ECS worker desired/running count mismatch;
- `telemetry_scheduler_iteration_failed`, ingestion-run failure, and repeated safe provider errors;
- enabled connection with no success/telemetry/checkpoint beyond cadence;
- retry storms, lease recovery, partial runs, and rejection-ratio spikes;
- stale/unmapped/problem signal counts and mapping failures;
- Secrets Manager access/ownership/version failures and controlled-egress denials;
- `telemetry_schema_readiness_failure` or runtime configuration failure;
- post-ingestion analysis failures or repeated insufficient authority/coverage.

Do not use connection credentials, secret references, full source URLs, external payloads, or raw telemetry as metric dimensions.

### Separately approved deployment sequence

1. Freeze the reviewed application artifact/revision and record current API, worker, frontend, and database rollback points.
2. Rehearse migrations and concurrent lease/checkpoint tests against disposable PostgreSQL using `NERAIUM_TEST_POSTGRES_DSN`.
3. Approve and apply database role/network changes; take a production snapshot.
4. Stop/hold the telemetry worker path and apply migrations 002, 003, 004 with the migration identity; run all three structural verifiers with the application identity.
5. Provision/tag the telemetry secret namespace and apply least-privilege API/worker/KMS policies. Establish the approved dynamic-write or pre-provisioned-binding mode.
6. Apply and independently verify controlled egress. Register any reviewed historian template/executor only if that provider is part of the approved rollout.
7. Register new API and worker task definitions with the telemetry DSN secret and non-secret settings. Keep legacy compatibility and legacy polling off.
8. Deploy the API revision first with telemetry schema readiness green, then deploy a worker revision with a controlled desired count. Confirm both revisions use the same database authority and build SHA.
9. Deploy the reviewed frontend so Data Connections is the production onboarding surface and historical import remains hidden/admin-gated.
10. In a non-production or explicitly approved pilot facility, execute create -> credential -> validate -> discover -> map -> enable -> ingest -> canonical observation -> SII -> Results -> Finding Review -> Investigation -> Evidence Record using controlled synthetic telemetry.
11. Enable pilot customer connections gradually and watch telemetry health, checkpoint progress, rejection/retry rates, database growth, and analysis outcomes before broadening rollout.

Every step above changes production state and requires separate approval. Do not automatically deploy, modify IAM, mutate the database, change DNS, or touch `demo.neraium.com`.

### Post-deploy verification

Verify all of the following before declaring the feature available:

- `/api/health` and `/api/ready` are healthy on the direct backend and `app.neraium.com` API route;
- API and worker startup contain no telemetry schema/runtime failure and report the expected build SHA/role;
- an authenticated facility member sees only that facility's connections; a second-tenant probe receives opaque not-found/empty results;
- provider discovery advertises retrieval-only capability and reports historian unavailable unless explicitly registered;
- credential response, logs, errors, audit, evidence, and browser storage contain no value, ARN, binding ID, or internal reference;
- SSRF probes and redirects remain denied from the deployed task network, and the controlled egress layer independently blocks private/metadata destinations;
- validation distinguishes reachability and authentication; connection health additionally distinguishes telemetry arrival, mapping, quality, and checkpoint state;
- discovered tags remain unmapped/disabled until an authorized mapping with explicit unit/time/cadence is approved;
- the worker obtains one lease, persists an idempotent page plus checkpoint, records partial rejections without losing accepted siblings, and resumes after a controlled restart;
- a bounded backfill is resumable and uses the same canonical pipeline;
- one canonical system window invokes SII once and the resulting finding/evidence traces to exact observations, mapping revision, connection, run, and timestamps;
- stable and insufficient-evidence outcomes do not manufacture findings or imply that individual sensors are normal;
- CloudWatch telemetry alarms and safe dashboards receive expected events/counters without sensitive payloads.

If any check fails, stop enabling new connections, disable pilot connections through the scoped API where safe, hold the worker, and use the forward-fix/application-rollback posture in [Database migrations](database-migrations.md#rollback-posture). Do not drop the telemetry schema or delete evidence.

## Deployment Order

For releases without production telemetry, the existing deployment order remains below. A release that enables production telemetry must first complete the separately approved sequence above; the current workflows do not do that automatically.

1. Push the reviewed release branch through the normal protected-main process.
2. Run the shared AWS bootstrap workflow or script when bucket, IAM, or log-group drift is possible.
3. Build and push the backend Docker image to Amazon ECR.
4. Deploy the backend through the GitHub Actions ECS workflow.
5. Confirm backend endpoints respond directly:
   - `https://<ecs-backend-url>/api/health`
   - `https://<ecs-backend-url>/api/ready`
6. Choose API routing pattern:
   - Pattern A: set `VITE_API_BASE_URL=https://<ecs-backend-url>` in Amplify build env.
   - Pattern B: configure CloudFront `/api/*` behavior to backend origin.
7. Deploy frontend through AWS Amplify Hosting.
8. Update backend `CORS_ORIGINS=https://<amplify-frontend-domain>` in ECS.
9. Verify production domain routing:
   - `curl -i https://app.neraium.com/api/health` should NOT return `server: AmazonS3` redirect behavior.
10. Verify the normal production Data Connections routes and the admin-gated historical compatibility routes on the production domain.
11. Test the controlled create -> validate -> discover -> map -> enable flow for an approved non-production/pilot connection. If historical compatibility is part of the release, test its permission boundary separately.

Historical compatibility routes include:

   - `POST /api/data/upload`
   - `GET /api/data/upload-status/<job_id>`
   - `GET /api/data/upload-stream/<job_id>`

## Local Validation Commands

Backend tests:

```powershell
.\\scripts\\test-backend.ps1
```

Frontend production build:

```powershell
.\\scripts\\build-frontend.ps1
```

Docker image build check:

```powershell
docker build -t neraium-backend:local .\\backend
```

Run the backend container locally on the production container port:

```powershell
docker run --rm -p 8080:8080 neraium-backend:local
```

Then check:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/api/health
```

## Deployment Boundaries

The existing AWS bootstrap does not create telemetry database identities or secrets, grant PostgreSQL privileges, change RDS networking, enable controlled egress, register a historian provider, or create telemetry-specific alarms. It only parameterizes exact DSN secret references and the scoped read policies needed by ECS. The deploy workflow applies the telemetry schema through a one-off migration task after those prerequisites exist. AWS bootstrap and ECS deployment automation otherwise live in checked-in scripts and GitHub workflows. Terraform remains deprecated and should not be used for active production ECS changes.

## Production Bootstrap

Bootstrap the shared S3 bucket, CloudWatch log groups, and ECS task roles with:

```bash
AWS_REGION=us-east-2 \
UPLOAD_STATE_BUCKET=<shared-s3-bucket> \
APP_TASK_ROLE_NAME=neraium-prod-task-app-role \
API_TOKEN_SECRET_ARN=arn:aws:secretsmanager:us-east-2:<account-id>:secret:<secret-name> \
AUTH_DATABASE_URL_SECRET_ARN=arn:aws:secretsmanager:us-east-2:<account-id>:secret:<legacy-postgres-dsn-secret> \
AUTH_DATABASE_SECRET_ARN=arn:aws:secretsmanager:us-east-2:<account-id>:secret:<rds-managed-secret> \
AUTH_DATABASE_KMS_KEY_ARN=arn:aws:kms:us-east-2:<account-id>:key/<rds-secret-key-id> \
TELEMETRY_DATABASE_URL_SECRET_ARN=arn:aws:secretsmanager:us-east-2:<account-id>:secret:<telemetry-application-dsn-secret> \
TELEMETRY_MIGRATION_DATABASE_URL_SECRET_ARN=arn:aws:secretsmanager:us-east-2:<account-id>:secret:<telemetry-migration-dsn-secret> \
NERAIUM_BOOTSTRAP_ADMIN_PASSWORD_SECRET_ARN=arn:aws:secretsmanager:us-east-2:<account-id>:secret:<bootstrap-admin-password-secret> \
TASK_EXECUTION_ROLE_NAME=neraium-prod-ecs-task-execution-role \
API_LOG_GROUP=/ecs/neraium-prod-api \
WORKER_LOG_GROUP=/ecs/neraium-prod-worker \
./scripts/bootstrap-production-aws.sh
```

GitHub Actions configuration required by the active deploy path:

```text
secret: NERAIUM_UPLOAD_STATE_BUCKET=<shared-s3-bucket>
NERAIUM_APP_TASK_ROLE_NAME=neraium-prod-task-app-role
NERAIUM_API_TOKEN_SECRET_ARN=arn:aws:secretsmanager:us-east-2:<account-id>:secret:<secret-name>
NERAIUM_AUTH_DATABASE_URL_SECRET_ARN=arn:aws:secretsmanager:us-east-2:<account-id>:secret:<legacy-postgres-dsn-secret>  # rollback compatibility
NERAIUM_TELEMETRY_DATABASE_URL_SECRET_ARN=arn:aws:secretsmanager:us-east-2:<account-id>:secret:<telemetry-application-dsn-secret>
NERAIUM_TELEMETRY_MIGRATION_DATABASE_URL_SECRET_ARN=arn:aws:secretsmanager:us-east-2:<account-id>:secret:<telemetry-migration-dsn-secret>
NERAIUM_BOOTSTRAP_ADMIN_EMAIL=<pilot-admin-email>
NERAIUM_BOOTSTRAP_ADMIN_PASSWORD_SECRET_ARN=arn:aws:secretsmanager:us-east-2:<account-id>:secret:<bootstrap-admin-password-secret>
```
