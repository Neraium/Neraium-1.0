# Neraium Architecture

## Current Scope

Neraium is starting as a small full-stack customer-facing application for cannabis cultivation operators and growers:

- A FastAPI backend exposes versioned API endpoints under `/api`.
- A Vite React frontend provides the first customer-facing app shell for controlled environment operations.
- Automated tests currently cover backend health behavior, placeholder facility systems, CSV upload validation, and lightweight data profiling.

This scaffold intentionally does not include authentication, a database, cloud deployment, assistant features, or legacy data schemas.

## Backend

The backend lives in `backend/app`.

```text
backend/app/main.py          FastAPI app factory, CORS, router registration
backend/app/routers/         Route modules grouped by responsibility
backend/requirements.txt     Python runtime and test dependencies
```

Initial endpoints:

- `GET /api/health` reports API availability.
- `GET /api/app` returns basic application metadata.
- `GET /api/facility/systems` returns hardcoded cultivation system placeholders.
- `POST /api/data/upload` accepts CSV files, validates the extension and structure, parses headers and preview rows, and returns upload metadata, timestamp profile, numeric column profiles, data quality, warnings, and readiness without permanent storage.

The app factory pattern keeps test setup simple and leaves room for future dependency wiring without changing the public ASGI entrypoint.

## Frontend

The frontend lives in `frontend`.

```text
frontend/index.html
frontend/src/main.jsx
frontend/src/App.jsx
frontend/src/styles.css
```

The current interface is a focused customer-facing shell for grow teams. It includes Overview, Facility Systems, Data Upload, and Reports sections.

The product direction is to help operators understand environmental drift before it becomes visible crop stress. Future workflows should explain changes across HVAC, humidity, airflow, irrigation, lighting, and sensor data in plain English for growers and facility operators.

Current frontend sections:

- Overview explains the product direction, shows API status, and displays placeholder cards for facility status, environmental drift, systems monitored, and latest report.
- Facility Systems lists hardcoded monitored systems for HVAC, humidity control, airflow, irrigation, lighting, and the sensor network.
- Data Upload validates CSV exports from historical facility data and sensor systems, then displays data quality, time range, numeric column profiles, columns, warnings, readiness, and preview rows.
- Reports lists placeholder report types for Environmental Drift Summary, System Coupling Review, and Operator Action Report.

CSV ingestion currently parses uploaded files in memory only. It does not persist data, create facility records, or run the Neraium engine. Profiling is deterministic and limited to basic usability checks for cultivation sensor exports.

## Local Integration

During local development:

- Backend: `http://127.0.0.1:8010`
- Frontend: `http://127.0.0.1:3010`

CORS is configured in the backend for the local frontend origins.

## Near-Term Extension Points

Future work should add capabilities in small, explicit layers:

- Authentication when pilot access requirements are defined.
- Persistence when the first durable customer data model is defined.
- Deployment configuration when the target environment is selected.
- Controlled environment operations workflows once the API contracts are clear.
