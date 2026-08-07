# Neraium Backend

FastAPI application for customer-facing Neraium API endpoints used by commercial water system operators.

The backend supports read-only operational intelligence for commercial pools, resort water systems, treatment, chilled water loops, pumps and filtration, and future cooling tower workflows.

## Local Setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
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
- `CORS_ORIGINS` defaults to local frontend origins and `https://app.neraium.com`.
- `CORS_ORIGIN_REGEX` defaults to `^https://([a-z0-9-]+\.)?neraium\.com$`.
- `NERAIUM_DEFAULT_TELEMETRY_URL` defaults to an empty value; set it only when a customer REST telemetry source should be polled.
- `NERAIUM_RUNTIME_DIR` defaults to `backend/app/runtime`.
- `NERAIUM_UPLOAD_CHUNK_SIZE_ROWS` defaults to `10000`.
- CSV validation scans the complete file. Analysis keeps a bounded sample controlled by `NERAIUM_MAX_INGESTION_ANALYSIS_ROWS` (default `100000`).
- `NERAIUM_MAX_UPLOAD_SIZE_BYTES` defaults to `262144000` (250 MiB) for multipart uploads through the API.
- `NERAIUM_MAX_LARGE_UPLOAD_SIZE_BYTES` defaults to `536870912` (512 MiB). Larger supported CSVs use `POST /api/data/upload-session`, a presigned browser-to-S3 `PUT`, and `POST /api/data/upload-session/{id}/complete`.

For Amazon ECS Express Mode / ECS Fargate, set `APP_ENV=production`, `BACKEND_HOST=0.0.0.0`, `BACKEND_PORT=8080`, `CORS_ORIGINS` to the deployed Amplify frontend origin, `CORS_ORIGIN_REGEX` to `^https://([a-z0-9-]+\.)?neraium\.com$`, and `NERAIUM_RUNTIME_DIR` to the container's writable runtime path. Do not set `NERAIUM_START_DATA_POLLER=true` unless a customer REST telemetry source has been explicitly configured.

## Container Build

The backend includes a Dockerfile for Amazon ECS Express Mode / ECS Fargate preparation. The container serves `app.main:app` with uvicorn and defaults to port `8080`.

```powershell
docker build -t neraium-backend:local .\backend
docker run --rm -p 8080:8080 neraium-backend:local
```

## Endpoints

- `GET /api/health` returns API availability.
- `GET /api/app` returns basic app metadata.
- `GET /api/facility/systems` returns the active domain profile, including commercial water system categories by default.
- `POST /api/data/upload` accepts CSV/JSON telemetry up to the direct-upload limit plus an explicit workflow. `create_baseline` and `extend_baseline` use the dedicated Behavioral Digital Model builder; `analyze_new_data` uses the SII analysis path and requires an active model. Baseline construction never generates SII findings or evidence.
- `POST /api/data/upload-session` and `POST /api/data/upload-session/{id}/complete` implement the large-CSV direct-to-object-storage path, preserve the selected workflow, and bind the resulting job to that upload session.
- `GET /api/data/baselines` returns the active model and latest candidate. Baseline job results and approval use `/api/data/baselines/jobs/{job_id}` and `/api/data/baselines/candidates/{model_id}/approve`.
- `GET /api/data/evidence-packages/{package_id}/related-packages` returns the authenticated, read-only Evidence Package Correlation v1 related-package set.

Uploaded CSV files are deleted after processing completes or fails. Job metadata and latest SII state are written under `NERAIUM_RUNTIME_DIR`. Schema mapping uses deterministic keyword matching only. Baseline comparison uses the first 20% of rows and last 20% of rows for descriptive drift checks only. Neraium SII v1 is deterministic and returns signals, system-level evidence, corroboration level, persistence assessment, recommended checks, limitations, and audit trace without prediction or root-cause claims.

## Tests

From the repository root:

```powershell
$env:PYTHONPATH = ".\backend"
python -m pytest tests
```
