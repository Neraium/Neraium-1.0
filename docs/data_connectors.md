# Connector Boundaries

Neraium has two connector surfaces with different purposes. Do not treat them as one production registry.

## Ongoing production telemetry

The production Data Connections workflow uses the retrieval-only provider contract documented in [Production Telemetry Connections](TELEMETRY_CONNECTIONS.md).

| Provider | Availability | Safety boundary |
|---|---|---|
| `https_telemetry` | Implemented; shared environments require approved controlled egress | Public HTTPS/443, `GET` only, server-resolved credentials, DNS/IP validation, no redirects/proxy inheritance, bounded pages/records/bytes/time/retries |
| `historian_template` | Unavailable until server startup registers a reviewed template/executor | Server-owned template and network profile, bounded typed parameters, no browser SQL/DSN/path/host |

Production providers validate, discover, retrieve incremental pages, optionally retrieve bounded backfill, and report safe health. They contain no SII/classification logic and expose no command, setpoint, acknowledgement, actuator, or write method.

Retrieved records pass through intentional signal mapping, explicit unit/time/quality normalization, canonical PostgreSQL persistence, and one source-neutral system-window SII handoff. Signals that are not approved and mapped remain analysis-ineligible.

## Historical/manual compatibility connectors

The legacy registry retains these adapters for existing bounded historical workflows and tests:

- `csv`
- `rest`
- `database`

They are not recurring production telemetry providers and are not advertised by `GET /api/data-connections/providers`. The legacy REST model can represent browser-configured methods/headers/bodies, and the legacy database model can represent DSNs/queries/paths; for that reason they must never be wired into the production connection scheduler. Shared environments tombstone the complete `/api/connectors/*` compatibility router before request parsing, including descriptors, tests, CSV upload, ingest, and global health. The older unscoped `/api/telemetry/*` and `/api/live-analysis/*` SQLite APIs are also local-only and return `410` in staging/production. Only the facility-scoped Data Connections repository and canonical analysis seam are production-authoritative.

MQTT, OPC UA, BACnet, Modbus, and vendor placeholders are unavailable. Their presence in compatibility descriptors is not evidence that a live integration exists.

## Adding a production provider

A new provider must:

1. implement only the retrieval capabilities in `backend/app/connectors/base.py`;
2. accept browser input only through a strict, allow-listed public model;
3. keep targets, templates, queries, network profiles, and credentials server-owned where required;
4. resolve credentials through the opaque telemetry secret abstraction;
5. enforce per-request and aggregate budgets and return sanitized stable errors;
6. preserve source timestamps, units, quality, external tag/event identity, and bounded provenance;
7. use the existing worker lease/checkpoint pipeline and canonical SII handoff without connector-specific analysis;
8. add tenant-isolation, read-only, SSRF/egress, secret-redaction, retry/backfill, and contract tests;
9. remain unavailable until the deployment capability and required infrastructure have been reviewed and configured.

Never adapt a provider by exposing arbitrary SQL, DSN, path, URL, HTTP method/body/header, filesystem access, or OT write/control functionality to a browser request.
