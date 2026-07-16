# Data Connectors

## Purpose

The Data Connectors layer gives Neraium a stable ingestion boundary for customer telemetry. Connectors collect data from external systems, normalize it into a shared schema, and hand it off to the existing Neraium API and intelligence flow without embedding engine logic inside the connector code.

## Architecture

Customer system  
-> Connector  
-> Normalized telemetry schema  
-> Existing Neraium engine and API  
-> Dashboard

Connectors are responsible for transport, basic validation, and normalization only. They do not make intelligence decisions, score drift, or interpret facility conditions.

## Supported connector types

- `csv`: functional. Handles local CSV upload and normalization.
- `rest`: functional. Polls a REST endpoint and normalizes JSON telemetry payloads.
- `database`: functional. Runs bounded read-only queries against SQLite or PostgreSQL and normalizes result rows.
- `mqtt`: scaffold only.
- `opcua`: scaffold only.
- `bacnet`: scaffold only.

## Normalized telemetry schema

Each normalized record contains:

- `source_id`
- `system_id`
- `sensor_id`
- `sensor_name`
- `value`
- `unit`
- `timestamp`
- `quality_status`
- `metadata`

Timestamps are parsed through the shared backend timestamp parser and normalized to a consistent ISO-style representation before records leave the connector boundary.

## How to add a new connector

1. Create a class in `backend/app/connectors/` that extends `ConnectorBase`.
2. Implement:
   - `connect()`
   - `validate_connection()`
   - `fetch_historical()`
   - `stream_latest()`
   - `normalize()`
   - `health_check()`
3. Return `NormalizedConnectorBatch` and `NormalizedTelemetryRecord` objects from normalization.
4. Register the connector in `backend/app/connectors/registry.py`.
5. Add endpoint coverage and tests.

## Current limitations

- CSV normalization infers units from common sensor names when a unit is not supplied.
- REST ingestion currently expects a JSON list or a top-level `records`, `data`, `items`, or `telemetry` array.
- Database queries are limited to one `SELECT` or `WITH` statement, execute in a read-only database session, return at most 5,000 rows by default (configurable up to 10,000), and time out after 30 seconds by default (configurable from 1 to 120 seconds).
- The database account remains the security boundary for accessible PostgreSQL schemas and tables. Configure a dedicated least-privilege account with `SELECT` only on approved telemetry views; do not use an owner or administrative account. PostgreSQL transport requires TLS (`sslmode=require` by default; use `verify-full` with a trusted CA in production). SQLite system catalog reads are denied by the connector.
- MQTT, OPC UA, BACnet, and vendor-specific placeholder connectors expose health and lifecycle scaffolding but do not yet connect to live systems.
- The connector layer prepares normalized telemetry for the existing engine boundary; it does not yet orchestrate full historical backfill workflows or live industrial subscriptions.
