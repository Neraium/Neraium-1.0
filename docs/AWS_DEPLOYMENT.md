# AWS Deployment Preparation

This document captures the active AWS deployment path for Neraium-1.0. Production bootstrap and ECS deployment are handled by a checked-in AWS CLI script plus GitHub Actions. Terraform is inactive and not the production source of truth.

## Targets

- Backend: Amazon ECS Express Mode / ECS Fargate
- Backend container image registry: Amazon ECR
- Frontend: AWS Amplify Hosting
- Production backend port: `80`
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
5. Configure the container port as `80`.
6. Configure the health check path as `/api/health`.
7. Confirm the ECS-generated public HTTPS URL returns a healthy response:

```text
https://<ecs-backend-url>/api/health
```

Required backend environment variables:

```text
APP_ENV=production
BACKEND_HOST=0.0.0.0
BACKEND_PORT=80
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
NERAIUM_AUTH_DATABASE_URL=<postgresql-dsn-from-secrets-manager-on-api-task>
```

The ECS deployment workflow registers both task definitions directly with AWS CLI. It expects the production ECS cluster, API service, worker service, and both task-definition families to already exist, validates those resources before image build, and fails fast if any are missing or inactive. New revisions pin the entrypoint, process role, CORS, upload limits, JSON logging, build SHA, runtime path, shared-state bucket, log group, and secret references.

`.aws/task-definition.json` is a legacy reference artifact and is not registered by the active deployment workflow. The live task families are the deployment baseline. Their volume and mount definitions are preserved: each role must already have its own durable writable volume mounted at `/mnt/neraium-runtime` if runtime history must survive task replacement. Do not share a SQLite runtime database between API and worker tasks; use distinct per-role volumes or EFS access points.

```text
command=["python","-m","app.entrypoint"]
awslogs group=/ecs/neraium-prod-api or /ecs/neraium-prod-worker
```

Upload path audit: the API streams FastAPI `UploadFile` chunks to disk, the default backend cap is 250 MiB, `NERAIUM_MAX_UPLOAD_SIZE_BYTES=262144000` is injected by the deployment workflow, and the ALB idle timeout is extended for slower mobile transfers. No NGINX reverse proxy is deployed in this stack; if you add CloudFront/CDN, WAF managed body-size rules, or NGINX later, align those request-body limits at or above 250 MiB before enabling mobile file intake.

For split-role production ECS, do not rely on `NERAIUM_RUNTIME_DIR` for cross-task queue state. The queue and latest-upload state are shared through `NERAIUM_UPLOAD_STATE_BUCKET`.

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
- Ensure all methods are allowed for API behavior (GET/HEAD/OPTIONS/POST at minimum).

Required API routes to backend origin:

- `/api/data/upload`
- `/api/data/upload-status/*`
- `/api/data/upload-stream/*`

The local frontend default remains `http://127.0.0.1:8010` when `VITE_API_BASE_URL` is not set.

## Deployment Order

1. Push the latest GitHub `main` branch.
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
10. Verify upload pipeline routes on production domain:
   - `POST /api/data/upload`
   - `GET /api/data/upload-status/<job_id>`
   - `GET /api/data/upload-stream/<job_id>`
11. Test full CSV upload flow from live frontend.

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
docker run --rm -p 8080:80 neraium-backend:local
```

Then check:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/api/health
```

## Deployment Boundaries

This preparation intentionally does not add user accounts, database persistence, or changes to API response shapes. AWS bootstrap and ECS deployment automation now live in checked-in scripts and GitHub workflows. Terraform remains deprecated and should not be used for active production ECS changes.

## Production Bootstrap

Bootstrap the shared S3 bucket, CloudWatch log groups, and ECS task roles with:

```bash
AWS_REGION=us-east-2 \
UPLOAD_STATE_BUCKET=<shared-s3-bucket> \
APP_TASK_ROLE_NAME=neraium-prod-task-app-role \
API_TOKEN_SECRET_ARN=arn:aws:secretsmanager:us-east-2:<account-id>:secret:<secret-name> \
AUTH_DATABASE_URL_SECRET_ARN=arn:aws:secretsmanager:us-east-2:<account-id>:secret:<postgres-dsn-secret> \
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
NERAIUM_AUTH_DATABASE_URL_SECRET_ARN=arn:aws:secretsmanager:us-east-2:<account-id>:secret:<postgres-dsn-secret>
```
