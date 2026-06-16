# Neraium

**See system drift before it becomes operational failure.**

Neraium is a system intelligence platform for complex, telemetry-driven environments. It analyzes multivariable data to detect drift, instability, weak signals, and operational risk before conventional threshold alarms or visible symptoms reveal a problem.

The platform is designed for environments where many signals interact at once: facilities, equipment, controlled environments, infrastructure, industrial systems, building systems, and other operational networks. Cultivation is one active pilot domain, but the core product is broader than cultivation.

---

## What Neraium Does

Neraium helps operators answer four practical questions:

1. **What state is the system in?**
2. **What is drifting or behaving abnormally?**
3. **What evidence supports the finding?**
4. **What should the operator check next?**

Instead of treating each sensor as an isolated alarm, Neraium evaluates relationships across signals and looks for structural changes in system behavior.

Current capabilities include:

- Telemetry upload and validation
- CSV, TXT, and JSON ingestion paths
- Data quality checks
- Timestamp and signal profiling
- Baseline versus recent comparison
- Neraium SII v1 engine results
- Evidence summaries
- Operator-facing reports
- Replay-ready upload artifacts
- Audit events
- Runtime observability
- Data connection scaffolding
- Backend worker processing
- AWS ECS deployment preparation

---

## Core Use Cases

Neraium is built for operational environments where drift matters before failure becomes obvious.

Potential domains include:

- Controlled-environment agriculture
- Building automation
- HVAC and mechanical systems
- Industrial equipment
- Manufacturing processes
- Water systems
- Energy systems
- Facility operations
- Predictive maintenance
- Sensor-heavy operational networks

The current pilot workflows emphasize uploaded telemetry and read-only intelligence. Neraium does not control equipment at this stage. It analyzes data, produces evidence, and gives operators clearer direction on what to inspect.

---

## Pilot Workflow

A typical workflow looks like this:

1. Upload telemetry from a system, facility, room, controller, or exported dataset.
2. Neraium validates the file and checks basic data quality.
3. The platform profiles timestamps, numeric signals, and available system fields.
4. Baseline behavior is compared against recent behavior.
5. The SII engine produces a deterministic system intelligence result.
6. Neraium generates evidence, warnings, readiness indicators, replay artifacts, and an operator report.
7. Operators review what changed, what evidence supports it, and what should be checked next.

---

## Repository Structure

```text
backend/    FastAPI application, runtime services, upload processing, workers, and backend documentation
frontend/   Vite React customer-facing app shell and operator interface
docs/       Architecture, deployment, pilot, and implementation notes
scripts/    Local development and validation helper scripts
tests/      Backend tests
```

---

## Backend

The backend is a FastAPI application with runtime services for uploads, evidence, audit events, observability, data connections, replay, and worker processing.

Important API areas include:

- `GET /api/health`
- `GET /api/app`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/facility/systems`
- `POST /api/data/upload`
- Upload status and replay endpoints
- Evidence and audit endpoints
- Observability and readiness endpoints

Backend runtime state is written under `NERAIUM_RUNTIME_DIR`. Runtime storage includes upload jobs, upload queue records, evidence runs, audit events, latest payloads, and data connection records.

---

## Frontend

The frontend is a Vite React application for customer and operator workflows.

Current sections include:

- Overview
- Facility and system views
- Data upload
- Upload status and result review
- Operator reports
- Replay-oriented views
- Evidence and observability surfaces

The frontend runs locally at `http://127.0.0.1:3010` and calls the backend configured by `VITE_API_BASE_URL`.

---

## Prerequisites

- Python 3.11+
- Node.js 20+
- npm

---

## Backend Setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

The backend runs locally at:

```text
http://127.0.0.1:8010
```

---

## Frontend Setup

```powershell
cd frontend
npm install
npm run dev
```

The frontend runs locally at:

```text
http://127.0.0.1:3010
```

---

## Common Environment Variables

Backend defaults are provided for local development. Production should explicitly configure runtime storage, CORS, workers, and deployment settings.

Common variables include:

- `APP_ENV`
- `BACKEND_HOST`
- `BACKEND_PORT`
- `CORS_ORIGINS`
- `CORS_ORIGIN_REGEX`
- `NERAIUM_RUNTIME_DIR`
- `NERAIUM_PROCESS_ROLE`
- `NERAIUM_START_BACKGROUND_WORKERS`
- `NERAIUM_START_DATA_POLLER`
- `NERAIUM_MAX_UPLOAD_SIZE_BYTES`
- `NERAIUM_MAX_PENDING_UPLOAD_JOBS`
- `NERAIUM_UPLOAD_STATE_BUCKET`
- `VITE_API_BASE_URL`

---

## Tests and Validation

Run backend tests from the repository root:

```powershell
$env:PYTHONPATH = ".\backend"
python -m pytest tests
```

Run frontend validation from the frontend directory:

```powershell
cd frontend
npm run lint
npm run build
npm run test
```

Helper scripts are available from the repository root:

```powershell
.\scripts\start-backend.ps1
.\scripts\start-frontend.ps1
.\scripts\test-backend.ps1
.\scripts\build-frontend.ps1
```

---

## Deployment

Neraium includes AWS deployment preparation for a backend API service and worker service using ECS/Fargate and ECR.

Deployment notes and runbooks are available in:

- `docs/AWS_DEPLOYMENT.md`
- `docs/DEPLOYMENT_RUNBOOK.md`
- `docs/PRODUCTION_ACCEPTANCE_CHECKLIST.md`
- `docs/PRODUCTION_OPERATOR_FLOW_CHECKLIST.md`

Local backend development runs on port `8010`. Local frontend development runs on port `3010`. The backend container is prepared for cloud deployment on port `80`.

---

## Current Status

Neraium 1.0 is the active production-oriented pilot foundation.

The current platform supports read-only telemetry analysis, upload-based workflows, deterministic SII engine results, evidence generation, replay artifacts, audit logging, runtime observability, authentication, and cloud deployment preparation.

The next major focus areas are broader data connectors, stronger production authentication and authorization, expanded test coverage, improved replay workflows, and pilot-specific operator reporting.

---

## Vision

Neraium is building a general-purpose system intelligence layer for operational environments.

The long-term goal is to help teams understand complex systems earlier, act before failure becomes visible, and reduce downtime, waste, crop loss, equipment failure, and operational uncertainty across multiple industries.
