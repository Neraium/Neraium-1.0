# Neraium

**See system drift before it becomes operational failure.**

Neraium is a system intelligence platform for complex, telemetry-driven environments. It analyzes multivariable data to detect drift, instability, weak signals, and operational risk before conventional threshold alarms or visible symptoms reveal a problem.

The platform is designed for environments where many signals interact at once: facilities, equipment, controlled environments, infrastructure, industrial systems, building systems, and other operational networks. Controlled-environment agriculture is one possible application area, but Neraium is not limited to cultivation.

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
- Continuous backend and frontend validation through GitHub Actions

---

## Demo Path

A strong demo should show Neraium as an evidence-backed system intelligence workflow, not just a dashboard.

Recommended flow:

1. Open the system status view.
2. Upload a telemetry export.
3. Show validation, queued worker visibility, and processing progress.
4. Open the operator finding or report.
5. Explain what changed, why it matters, and what the operator should inspect next.
6. Open Evidence Replay to show the behavior change over time.
7. Close by explaining that the same intelligence layer applies across telemetry-heavy operational environments.

Demo and screenshot planning docs:

- `docs/DEMO_SCRIPT.md`
- `docs/SCREENSHOT_CHECKLIST.md`

---

## Core Use Cases

Neraium is built for operational environments where drift matters before failure becomes obvious.

Potential domains include:

- Building automation
- HVAC and mechanical systems
- Industrial equipment
- Manufacturing processes
- Water systems
- Energy systems
- Facility operations
- Predictive maintenance
- Controlled environments
- Sensor-heavy operational networks

The current workflows emphasize uploaded telemetry and read-only intelligence. Neraium does not control equipment at this stage. It analyzes data, produces evidence, and gives operators clearer direction on what to inspect.

---

## Workflow

A typical workflow looks like this:

1. Upload telemetry from a system, facility, asset, controller, or exported dataset.
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
python -m pip install -r requirements-dev.txt
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

GitHub Actions CI now validates the backend and frontend on push to `main` and on pull requests. The CI workflow runs backend tests, frontend linting, frontend build, and frontend unit tests.

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

## Production Hardening

Before broader production use, review `docs/PRODUCTION_ACCEPTANCE_CHECKLIST.md` for authentication, authorization, runtime storage, CI, screenshot/demo assets, observability, deployment, and operator-flow acceptance checks.

Current hardening focus areas include:

- Confirming runtime database persistence across API and worker restarts
- Confirming auth/session persistence through the dedicated auth database
- Verifying multi-task or multi-worker deployment behavior
- Using Postgres for production auth/session state while keeping SQLite fallback for tests and local development
- Keeping README/demo screenshots current with the deployed UI
- Keeping browser clients free of build-time shared API secrets
- Expanding dependency security policy from critical CVE blocking to broader release governance

---

## Current Status

Neraium 1.0 is the active production-oriented foundation for system intelligence workflows.

The current platform supports read-only telemetry analysis, upload-based workflows, deterministic SII engine results, evidence generation, replay artifacts, audit logging, runtime observability, authentication, CI validation, and cloud deployment preparation.

The next major focus areas are broader data connectors, multi-instance shared runtime storage, expanded test coverage, improved replay workflows, and operator reporting.

Current Phase 3 hardening status:

- Auth users and sessions persist in a dedicated auth database instead of `auth_store.json`
- The auth store uses local SQLite by default and Postgres when `NERAIUM_AUTH_DATABASE_URL` is configured
- Legacy JSON auth state is migrated forward on first boot into the auth database
- Admin APIs can list users/sessions, activate or deactivate users, and revoke sessions
- Observability now includes auth user/session counts and CI includes dependency security scanning

Current Phase 2 hardening status:

- Protected write routes require an authenticated session or configured service token in production
- Role boundaries are enforced in production for operator and admin surfaces
- Bootstrap pilot accounts can be provisioned through environment variables
- Login attempts are rate-limited in production and auth session events are audited

Current Phase 1 hardening status:

- Frontend requests no longer source a shared API token from `VITE_` build-time environment
- Production startup now requires an explicit `NERAIUM_RUNTIME_DIR`
- Shared upload-state persistence failures are logged instead of silently swallowed
- Security documentation has been reduced to match the controls currently implemented

---

## Vision

Neraium is building a general-purpose system intelligence layer for operational environments.

The long-term goal is to help teams understand complex systems earlier, act before failure becomes visible, and reduce downtime, waste, equipment failure, and operational uncertainty across multiple industries.
