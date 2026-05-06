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

## Endpoints

- `GET /api/health` returns API availability.
- `GET /api/app` returns basic app metadata.
- `GET /api/facility/systems` returns hardcoded cultivation system placeholders.
- `POST /api/data/upload` accepts a CSV file, validates structure, and returns metadata, preview rows, timestamp profile, numeric column profiles, baseline comparison, warnings, and data readiness.

CSV uploads are parsed in memory only. The backend does not save uploaded files permanently and does not run the Neraium engine. Baseline comparison uses the first 20% of rows and last 20% of rows for descriptive drift checks only.

## Tests

From the repository root:

```powershell
$env:PYTHONPATH = ".\backend"
python -m pytest tests
```
