# Neraium Architecture

## Current Scope

Neraium is a full-stack platform for commercial water-system operators. Systemic Infrastructure Intelligence (SII) is the intelligence Neraium applies to infrastructure telemetry.

- A FastAPI backend exposes authenticated API endpoints under `/api`.
- A Vite React frontend provides operator, administration, and evidence-review workspaces.
- Role-based access distinguishes viewers, operators, and administrators.
- Runtime persistence stores analysis jobs, results, evidence, audit records, connector state, and sessions.
- Read-only CSV, REST API, and database inputs support bounded telemetry analysis. Additional connector types are explicitly marked as planned.

## Backend

The backend lives in `backend/app`.

```text
backend/app/main.py          FastAPI app factory, security middleware, and router registration
backend/app/routers/         Authenticated routes grouped by product workflow
backend/app/services/        Dataset ingestion, SII analysis, evidence, persistence, and connector services
backend/app/engine/          Deterministic Systemic Infrastructure Intelligence engine
backend/requirements.txt     Python runtime and test dependencies
```

Major API workflows include authentication and session management, system discovery, dataset import, connector setup and health, analysis status and retry, insights, evidence review and export, administration, observability, and behavior replay.

CSV imports are validated and processed through a bounded analysis workflow. Source files are deleted after processing; analysis metadata, results, evidence, and the latest SII state are retained in the configured runtime directory. SII compares behavior windows and system relationships. It does not claim root cause, predict failure, or control equipment.

## Frontend

The frontend lives in `frontend`. The operator workspace is organized around distinct product objects:

- **Systems** are operational equipment or processes discovered from telemetry behavior.
- **Datasets** are bounded telemetry collections imported for analysis.
- **Connectors** are configured read-only integrations with their own health state.
- **Analyses** are individual SII executions against datasets.
- **Insights** are operator-facing behavior changes that may warrant investigation.
- **Evidence** is the observed telemetry and comparison context supporting an insight.

The Command Center prioritizes insights and discovered systems. Datasets & Connectors manages data availability. Analysis Details exposes analysis metadata and support diagnostics. Help & Status explains the product language and current service state. Administration provides governance records, user access, and session controls.

## Local Integration

During local development:

- Backend: `http://127.0.0.1:8010`
- Frontend: `http://127.0.0.1:3010`

Runtime configuration is centralized in `backend/app/core/config.py` and `frontend/src/config.js`. AWS deployment preparation is documented in `docs/AWS_DEPLOYMENT.md`.

## Product Language

`docs/PRODUCT_LANGUAGE.md` is the source of truth for Neraium and SII terminology, entity names, health states, severity, and sanitized operator-facing messages.
