# AWS Deployment Preparation

This document captures the current deployment preparation for Neraium-1.0. It does not deploy resources automatically and does not add infrastructure-as-code yet.

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
python -m uvicorn app.main:app --host ${BACKEND_HOST:-0.0.0.0} --port ${BACKEND_PORT:-80}
```

Backend deployment notes:

1. Build the backend Docker image from the repository root:

```powershell
docker build -t neraium-backend:local .\backend
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
NERAIUM_MAX_ANALYSIS_ROWS=20000
NERAIUM_MAX_SII_ROWS=5000
NERAIUM_MAX_UPLOAD_SIZE_BYTES=262144000
NERAIUM_MAX_PENDING_UPLOAD_JOBS=50
```

Current backend behavior does not require a database, storage bucket, auth provider, AWS credentials in the app container, AI/LLM configuration, or shared access-code configuration. Add user identity and server-side sessions before broader customer access.

Upload path audit: the API streams FastAPI `UploadFile` chunks to disk, the default backend cap is 250 MiB, Terraform passes `NERAIUM_MAX_UPLOAD_SIZE_BYTES=262144000`, and the ALB idle timeout is extended for slower mobile transfers. No NGINX reverse proxy is deployed in this stack; if you add CloudFront/CDN, WAF managed body-size rules, or NGINX later, align those request-body limits at or above 250 MiB before enabling mobile file intake.

For production ECS, mount `NERAIUM_RUNTIME_DIR` to durable shared storage such as EFS if upload job status and latest SII state must survive task replacement or multiple replicas. A single ephemeral container filesystem is acceptable only for local development and throwaway demos.

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

Required frontend environment variable:

```text
VITE_API_BASE_URL=https://<ecs-backend-url>
```

The local frontend default remains `http://127.0.0.1:8010` when `VITE_API_BASE_URL` is not set.

## Deployment Order

1. Push the latest GitHub `main` branch.
2. Build and push the backend Docker image to Amazon ECR.
3. Deploy the backend through Amazon ECS Express Mode / ECS Fargate.
4. Confirm `https://<ecs-backend-url>/api/health` works.
5. Deploy the frontend through AWS Amplify Hosting.
6. Set `VITE_API_BASE_URL=https://<ecs-backend-url>` in Amplify.
7. Update backend `CORS_ORIGINS=https://<amplify-frontend-domain>` in ECS.
8. Test the CSV upload flow from the live frontend.

## Local Validation Commands

Backend tests:

```powershell
.\scripts\test-backend.ps1
```

Frontend production build:

```powershell
.\scripts\build-frontend.ps1
```

Docker image build check:

```powershell
docker build -t neraium-backend:local .\backend
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

This preparation intentionally does not add user accounts, database persistence, object storage, deployment automation, AWS infrastructure templates, or changes to API response shapes.
