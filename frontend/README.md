# Neraium Frontend

Vite React application shell for the customer-facing Neraium product for commercial water system operators.

The app shell positions Neraium around relationship drift in commercial water systems, with focus areas including pools, resort water systems, treatment, chilled-water loops, pumps, filtration, and future cooling tower coverage.

## Sections

- Overview: product orientation, API status, and facility summary placeholders.
- Facility Systems: commercial water system categories and active domain-detected systems.
- Data Upload: CSV ingestion flow for historical facility data and sensor exports, with validation results, schema mapping, data quality, timestamp range, numeric profiles, baseline comparison, Neraium SII v1 engine result, operator report, warnings, readiness, and preview rows.
- Reports: placeholder report list plus the latest generated upload report for the current frontend session.

## Local Setup

```powershell
cd frontend
npm install
```

## Run

```powershell
npm run dev
```

The app runs at `http://127.0.0.1:3010`.

## Backend Connection

Frontend API configuration is centralized in `frontend/src/config.js`. By default, the frontend calls the local backend at `http://127.0.0.1:8010` for API health, facility systems, and CSV upload validation.

The Engine Result section displays system evidence by operational category, corroboration level, persistence assessment, recommended operator checks, limitations, and audit trace details from the upload response.

To use another backend URL, including the production ECS backend URL, set:

```powershell
$env:VITE_API_BASE_URL = "http://127.0.0.1:8010"
```

For AWS Amplify Hosting, set `VITE_API_BASE_URL` to the ECS-generated public HTTPS backend URL in the frontend build environment before running `npm run build`.

Do not inject shared API secrets into frontend build variables. Browser requests should rely on the authenticated session flow rather than a build-time token.

Production routing warning:

- If `https://app.neraium.com/api/*` resolves to static hosting (for example `301` with `server: AmazonS3`), frontend API calls will not reach backend workers.
- Either set `VITE_API_BASE_URL` to the backend URL, or configure CloudFront `/api/*` behavior to route to backend origin.
- Required backend-routed paths include `/api/data/upload`, `/api/data/upload-status/*`, and `/api/data/upload-stream/*`.

## Build

```powershell
npm run build
```
