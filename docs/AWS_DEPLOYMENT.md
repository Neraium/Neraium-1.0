# AWS Deployment Preparation

This document captures the current deployment preparation for Neraium-1.0. It does not deploy resources automatically.

## Targets

- Backend: AWS App Runner
- Frontend: AWS Amplify Hosting or another static host for the Vite build output
- Production backend port: `8080`
- Local backend port: `8010`
- Local frontend port: `3010`

## Backend: AWS App Runner

The backend includes `backend/Dockerfile` for container deployment. It runs the FastAPI app with:

```text
python -m uvicorn app.main:app --host ${BACKEND_HOST:-0.0.0.0} --port ${BACKEND_PORT:-8080}
```

App Runner setup notes:

1. Build from the `backend` directory using `backend/Dockerfile`.
2. Configure the service port as `8080`.
3. Use `/api/health` as the health check endpoint.
4. Confirm the deployed service returns a healthy response at `https://<app-runner-url>/api/health`.
5. Keep local development on `127.0.0.1:8010`; production port `8080` is only for the container runtime.

Required backend environment variables:

```text
APP_ENV=production
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8080
CORS_ORIGINS=https://<amplify-frontend-domain>
```

Current backend behavior does not require a database, storage bucket, auth provider, AWS credentials, or AI/LLM configuration.

## Frontend: AWS Amplify Or Static Vite Build

The frontend is a static Vite React app. Production builds are created with:

```powershell
cd frontend
npm install
npm run build
```

Amplify setup notes:

1. Set the app root to `frontend` if Amplify is connected to the repository root.
2. Use `npm install` for dependency installation.
3. Use `npm run build` as the build command.
4. Publish the `frontend/dist` directory.
5. Set `VITE_API_BASE_URL` to the deployed App Runner backend URL, for example:

```text
VITE_API_BASE_URL=https://<app-runner-url>
```

The local frontend default remains `http://127.0.0.1:8010` when `VITE_API_BASE_URL` is not set.

Required frontend environment variables:

```text
VITE_API_BASE_URL=https://<app-runner-url>
```

## Local Validation Commands

Backend tests:

```powershell
.\scripts\test-backend.ps1
```

Frontend production build:

```powershell
.\scripts\build-frontend.ps1
```

Dockerfile syntax and image build check:

```powershell
docker build -t neraium-backend:local .\backend
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

This preparation intentionally does not add authentication, database persistence, object storage, deployment automation, AWS infrastructure templates, or changes to API response shapes.
