# Neraium Frontend

Vite React application shell for the customer-facing Neraium product for cannabis cultivation operators and growers.

The app shell positions Neraium around environmental drift in controlled grow facilities, with focus areas including HVAC, humidity, airflow, irrigation, lighting, and sensor data.

## Sections

- Overview: product orientation, API status, and facility summary placeholders.
- Facility Systems: placeholder monitored systems for cultivation operations.
- Data Upload: CSV ingestion placeholder for historical facility data and sensor exports.
- Reports: placeholder report list for the first customer-facing report structure.

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

By default, the frontend calls `http://127.0.0.1:8010/api/health`.

To use another backend URL, set:

```powershell
$env:VITE_API_BASE_URL = "http://127.0.0.1:8010"
```

## Build

```powershell
npm run build
```
