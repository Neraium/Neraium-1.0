# Neraium Frontend

Vite React application shell for the customer-facing Neraium product for cannabis cultivation operators and growers.

The app shell positions Neraium around environmental drift in controlled grow facilities, with focus areas including HVAC, humidity, airflow, irrigation, lighting, and sensor data.

## Sections

- Overview: product orientation, API status, and facility summary placeholders.
- Facility Systems: placeholder monitored systems for cultivation operations.
- Data Upload: CSV ingestion flow for historical facility data and sensor exports, with validation results, cultivation mapping, data quality, timestamp range, numeric profiles, baseline comparison, engine result, operator report, warnings, readiness, and preview rows.
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

By default, the frontend calls the local backend at `http://127.0.0.1:8010` for API health, facility systems, and CSV upload validation.

To use another backend URL, set:

```powershell
$env:VITE_API_BASE_URL = "http://127.0.0.1:8010"
```

## Build

```powershell
npm run build
```
