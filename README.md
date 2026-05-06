# Neraium

Neraium is a customer-facing application for infrastructure intelligence in physical systems.

This repository is the production-oriented foundation for pilot customer access. It currently contains a FastAPI backend, a Vite React frontend, initial tests, and architecture notes.

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
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The backend exposes:

- `GET /api/health`
- `GET /api/app`

## Frontend Setup

```powershell
cd frontend
npm install
npm run dev
```

The frontend runs at `http://127.0.0.1:3000` and calls the local backend at `http://127.0.0.1:8000`.

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
