# Neraium

Neraium helps cannabis cultivation teams detect and explain environmental drift before it becomes visible crop stress.

This repository is the production-oriented foundation for pilot customer access in controlled environment cannabis grow facilities. It currently contains a FastAPI backend, a Vite React frontend, initial customer app sections, initial tests, and architecture notes.

The product is focused on controlled environment operations across HVAC, humidity, airflow, irrigation, lighting, and sensor data.

## Repository Structure

```text
backend/    FastAPI application and backend documentation
frontend/   Vite React customer-facing app shell
docs/       Architecture and implementation notes
scripts/    Local development helper scripts
tests/      Backend tests
```

## Prerequisites

- Python 3.11+
- Node.js 20+
- npm

## Backend Setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

The backend exposes:

- `GET /api/health`
- `GET /api/app`
- `GET /api/facility/systems`
- `POST /api/data/upload`

Backend configuration is read from environment variables with local defaults:

- `APP_ENV=development`
- `BACKEND_HOST=127.0.0.1`
- `BACKEND_PORT=8010`
- `CORS_ORIGINS=http://127.0.0.1:3010,http://localhost:3010,https://app.neraium.com`
- `NERAIUM_RUNTIME_DIR=backend/app/runtime`
- `NERAIUM_UPLOAD_CHUNK_SIZE_ROWS=10000`
- `NERAIUM_MAX_ANALYSIS_ROWS=20000`
- `NERAIUM_MAX_SII_ROWS=5000`

## Frontend Setup

```powershell
cd frontend
npm install
npm run dev
```

The frontend runs at `http://127.0.0.1:3010` and calls the API configured by `VITE_API_BASE_URL`. The local default remains `http://127.0.0.1:8010`.

Current frontend sections:

- Overview
- Facility Systems
- Data Upload with CSV validation, cultivation mapping, profiling, baseline comparison, Neraium SII v1 engine result, operator report, and preview
- Reports

CSV uploads are parsed for validation, preview, cultivation column mapping, lightweight data profiling, simple baseline comparison, a deterministic Neraium SII v1 engine result, and a plain-English operator report only. Uploaded CSV files are deleted after the job completes or fails; job metadata and latest SII state are written under `NERAIUM_RUNTIME_DIR`. The upload response includes data quality, timestamp range, cultivation mapping, numeric column profiles, baseline versus recent averages, `engine_result`, warnings, readiness, and `operator_report`. `engine_result` includes system-level evidence, corroboration level, persistence assessment, recommended operator checks, limitations, and audit trace details. No non-deterministic analysis is run at this stage.

## Tests

```powershell
$env:PYTHONPATH = ".\backend"
python -m pytest tests
```

## Helper Scripts

From the repository root:

```powershell
.\scripts\start-backend.ps1
.\scripts\start-frontend.ps1
```

Additional validation helpers:

```powershell
.\scripts\test-backend.ps1
.\scripts\build-frontend.ps1
```

## AWS Deployment Preparation

Deployment preparation notes are in `docs/AWS_DEPLOYMENT.md`. The backend container is prepared for Amazon ECS Express Mode / ECS Fargate on port `80`; local backend development remains on port `8010`, and local frontend development remains on port `3010`.
