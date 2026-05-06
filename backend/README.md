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

## Tests

From the repository root:

```powershell
$env:PYTHONPATH = ".\backend"
python -m pytest tests
```
