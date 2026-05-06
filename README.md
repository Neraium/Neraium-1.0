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

## Frontend Setup

```powershell
cd frontend
npm install
npm run dev
```

The frontend runs at `http://127.0.0.1:3010` and calls the local backend at `http://127.0.0.1:8010`.

Current frontend sections:

- Overview
- Facility Systems
- Data Upload with CSV validation and preview
- Reports

CSV uploads are parsed in memory for validation and preview only. Files are not stored permanently, and no analysis engine is run at this stage.

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
