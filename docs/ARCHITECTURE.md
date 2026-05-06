# Neraium Architecture

## Current Scope

Neraium is starting as a small full-stack customer-facing application:

- A FastAPI backend exposes versioned API endpoints under `/api`.
- A Vite React frontend provides the first customer-facing app shell.
- Automated tests currently cover backend health behavior.

This scaffold intentionally does not include authentication, a database, cloud deployment, AI assistant features, or legacy data schemas.

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

The app factory pattern keeps test setup simple and leaves room for future dependency wiring without changing the public ASGI entrypoint.

## Frontend

The frontend lives in `frontend`.

```text
frontend/index.html
frontend/src/main.jsx
frontend/src/App.jsx
frontend/src/styles.css
```

The current interface is a focused customer-facing shell. It displays the Neraium product name, the product subtitle, and live API availability from the backend health endpoint.

## Local Integration

During local development:

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:3000`

CORS is configured in the backend for the local frontend origins.

## Near-Term Extension Points

Future work should add capabilities in small, explicit layers:

- Authentication when pilot access requirements are defined.
- Persistence when the first durable customer data model is defined.
- Deployment configuration when the target environment is selected.
- Infrastructure intelligence workflows once the API contracts are clear.
