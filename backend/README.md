# Neraium Backend

FastAPI application for customer-facing Neraium API endpoints used by cannabis cultivation operators and growers.

The backend currently supports the first app scaffold for controlled environment operations. Product-facing metadata should stay focused on helping grow teams detect and explain environmental drift before it becomes visible crop stress.

## Local Setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Run

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Local helper script from the repository root:

```powershell
.\scripts\start-backend.ps1
```

Configuration is centralized in `backend/app/core/config.py` and read from environment variables:

- `APP_ENV` defaults to `development`.
- `BACKEND_HOST` defaults to `127.0.0.1`.
- `BACKEND_PORT` defaults to `8010`.
- `CORS_ORIGINS` defaults to `http://127.0.0.1:3010,http://localhost:3010`.

For Amazon ECS Express Mode / ECS Fargate, set `APP_ENV=production`, `BACKEND_HOST=0.0.0.0`, `BACKEND_PORT=8080`, and `CORS_ORIGINS` to the deployed Amplify frontend origin.

## Container Build

The backend includes a Dockerfile for Amazon ECS Express Mode / ECS Fargate preparation. The container serves `app.main:app` with uvicorn and defaults to port `8080`.

```powershell
docker build -t neraium-backend:local .\backend
docker run --rm -p 8080:8080 neraium-backend:local
```

## Endpoints

- `GET /api/health` returns API availability.
- `GET /api/app` returns basic app metadata.
- `GET /api/facility/systems` returns hardcoded cultivation system placeholders.
- `POST /api/data/upload` accepts a CSV file, validates structure, and returns metadata, preview rows, cultivation mapping, timestamp profile, numeric column profiles, baseline comparison, deterministic Neraium SII v1 engine result, warnings, data readiness, and a plain-English operator report.

CSV uploads are parsed in memory only. The backend does not save uploaded files permanently. Cultivation mapping uses deterministic keyword matching only. Baseline comparison uses the first 20% of rows and last 20% of rows for descriptive drift checks only. Neraium SII v1 is deterministic and returns signals, system-level evidence, corroboration level, persistence assessment, recommended checks, limitations, and audit trace without prediction or root-cause claims.

## Tests

From the repository root:

```powershell
$env:PYTHONPATH = ".\backend"
python -m pytest tests
```
