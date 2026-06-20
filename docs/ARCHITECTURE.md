# Neraium Architecture

## Current Scope

Neraium is a full-stack customer-facing application for commercial water-system operators:

- A FastAPI backend exposes versioned API endpoints under `/api`.
- A Vite React frontend provides the customer-facing app shell for commercial water-system operations.
- Automated tests currently cover backend health behavior, placeholder facility systems, CSV upload validation, water-system and telemetry column mapping, lightweight data profiling, simple baseline comparison, deterministic Neraium SII v1 engine output, and deterministic operator report generation.

This scaffold intentionally does not include user accounts, a database, cloud deployment automation, assistant features, legacy data schemas, or private access-code gating.

## Backend

The backend lives in `backend/app`.

```text
backend/app/main.py          FastAPI app factory, CORS, router registration
backend/app/routers/         Route modules grouped by responsibility
backend/app/services/        Upload parsing, mapping, profiling, comparison, and report services
backend/app/engine/          Deterministic system intelligence engine v1
backend/requirements.txt     Python runtime and test dependencies
```

Initial endpoints:

- `GET /api/health` reports API availability.
- `GET /api/app` returns basic application metadata.
- `GET /api/facility/systems` returns monitored system placeholders for facility water operations.
- `POST /api/data/upload` accepts CSV files, validates the extension and structure, parses headers and preview rows, and returns upload metadata, water-system mapping, timestamp profile, numeric column profiles, baseline comparison, engine result, operator report, data quality, warnings, and readiness. Uploaded CSV files are deleted after processing; job metadata and latest SII state are retained under the configured runtime directory.

The app factory pattern keeps test setup simple and leaves room for future dependency wiring without changing the public ASGI entrypoint.

## Frontend

The frontend lives in `frontend`.

```text
frontend/index.html
frontend/src/main.jsx
frontend/src/App.jsx
frontend/src/styles.css
```

The current interface is a focused customer-facing shell for commercial water-system operators. It includes Overview, Facility Systems, Data Upload, and Reports sections.

The product direction is to help operators understand telemetry drift before it becomes operational water-system failure. Future workflows should explain changes across pumps, filtration, tanks, flow, pressure, temperature, chemistry, and equipment telemetry in plain English for water-system operators and facility teams.

Current frontend sections:

- Overview explains the product direction, shows API status, and displays placeholder cards for facility status, environmental drift, systems monitored, and latest report.
- Facility Systems lists hardcoded monitored systems for pumps, filtration, tanks, flow, pressure, treatment, chemistry, and equipment telemetry.
- Data Upload validates CSV exports from historical facility data and sensor systems, then displays water-system mapping, data quality, time range, numeric column profiles, baseline comparison, Neraium SII v1 engine result, operator report, columns, warnings, readiness, and preview rows.
- Reports lists placeholder report types for Environmental Drift Summary, System Coupling Review, and Operator Action Report, and shows the latest generated upload report for the current frontend session when one exists.

CSV ingestion streams uploaded files into a transient runtime upload file, processes representative windows for large batches, and deletes the uploaded CSV after completion or failure. It persists only job metadata and latest SII state in the configured runtime directory. It does not create facility records or run non-deterministic analysis. Water-system mapping, profiling, baseline comparison, Neraium SII v1 engine result, and operator reports are deterministic and limited to uploaded commercial water-system telemetry exports. Water-system mapping uses keyword matching against uploaded column names only. Baseline comparison uses the first 20% of rows as a simple baseline window and the last 20% as the recent window.

Neraium SII v1 treats the upload as commercial water-system behavior rather than generic anomaly detection. It groups evidence by operational telemetry category, counts corroborating numeric signals, evaluates whether recent-window drift appears persistent within the uploaded rows, and returns an audit trace with baseline/recent windows, columns analyzed, columns skipped, relationship checks attempted, and relationship checks skipped with reasons. Engine output and reports do not predict failures, water quality outcome, service impact, or root cause.

## Local Integration

During local development:

- Backend: `http://127.0.0.1:8010`
- Frontend: `http://127.0.0.1:3010`

CORS is configured in the backend for the local frontend origins.

Runtime configuration is centralized in `backend/app/core/config.py` for backend environment values and `frontend/src/config.js` for the frontend API base URL. AWS deployment preparation is documented in `docs/AWS_DEPLOYMENT.md`. The backend container is prepared for Amazon ECS Express Mode / ECS Fargate on port `8080`, while local development keeps the dedicated Neraium ports listed above.

## Near-Term Extension Points

Future work should add capabilities in small, explicit layers:

- User identity and role-based authorization before broader customer access.
- Persistence when the first durable customer data model is defined.
- Deployment configuration when the target environment is selected.
- Controlled environment operations workflows once the API contracts are clear.
