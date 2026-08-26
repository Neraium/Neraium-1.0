# Production Telemetry Connections

This document is the architecture and operating contract for ongoing telemetry at `app.neraium.com`. The implementation is present in this repository, but the AWS, IAM, network, database-migration, and deployment changes described below have **not** been applied by this work. They require a separate production approval.

Neraium learns the behavior of a defined physical system as a whole. Signals are evidence inputs to that system model; an individual signal is not the product unit and a connection is not healthy merely because authentication succeeded once.

## Product boundary

The production journey is:

```text
Connect telemetry source
  -> validate and discover telemetry
  -> define/select the physical system
  -> intentionally map assets and signals
  -> validate units, time, cadence, quality, and coverage
  -> establish behavioral reference history
  -> continue ingestion
  -> evaluate canonical system telemetry through SII
  -> Results / Operations Brief
  -> Finding Review
  -> Investigation
  -> Evidence Record
```

Historical file import is a compatibility/admin workflow, not the production onboarding path. It is absent from normal Data Connections navigation. In production, mutating upload routes require the administrative historical-upload permission. The underlying path remains available for existing baseline and compatibility workflows and must not be used as the transport for connected telemetry.

## Authority and physical hierarchy

The explicit hierarchy is:

```text
Tenant / Customer
  -> Facility
    -> System
      -> Asset / Equipment (optional for a system-level signal)
        -> Signal
```

The authenticated facility workspace is the server authority. `tenant_scope_id`, `workspace_id`, `resource_scope_id`, and `facility_id` are derived from authenticated context, not accepted as request-body authority. The current compatibility rule requires `facility_id == workspace_id`. `resource_scope_id` is deterministic for the tenant and facility workspace and is shared by every authorized operator in that facility; user identity is audit attribution, not a storage partition.

Every connection, secret binding, discovered signal, mapping, ingestion run, checkpoint, observation, rejection, health record, audit event, analysis window, and observation-to-window link is scoped to that authority. Natural source identifiers never grant scope. Out-of-scope and missing resources return the same opaque not-found behavior. Legacy/global rows are not assigned to a tenant and remain analysis-ineligible.

`asset_id` is the canonical telemetry field and resolves against the existing equipment authority. It may be omitted only when a signal legitimately belongs to the system as a whole. Keeping system and asset identities separate avoids flattening a facility into one model and leaves room for later relationships between already learned systems.

## Canonical data contract

The PostgreSQL `telemetry` schema is the shared authority for API and worker processes. Its main records are:

| Record | Purpose |
|---|---|
| `data_connections` | Scoped lifecycle, safe configuration, cadence, timezone, attempts, telemetry freshness, lease state |
| `connection_secret_bindings` | Internal opaque link to an owned AWS secret; excluded from public projections |
| `canonical_signal_concepts` | Versioned Neraium signal taxonomy and canonical units |
| `external_signals` | Source tags discovered under one scoped connection; unmapped and disabled by default |
| `signal_mappings` | Approved facility/system/asset/concept/unit/time/cadence mapping with actor, revision, and provenance |
| `ingestion_runs` | Validation, discovery, incremental, retry, and backfill work with bounded counters and safe errors |
| `connection_checkpoints` | Mode-specific cursor/high-water state with compare-and-swap revision |
| `normalized_observations` | Accepted canonical telemetry with exact source and mapping lineage |
| `observation_rejections` | Duplicate, quarantined, or rejected records with stable reason and occurrence counts |
| `connection_health` | Independent reachability, authentication, freshness, mapping, quality, and worker/checkpoint facets |
| `telemetry_audit_events` | Meaningful configuration and lifecycle actions, not per-sample noise |
| `analysis_authority_snapshots`, `analysis_windows`, `analysis_window_observations` | Server-attested system authority, one source-neutral SII execution, and exact observation lineage |

An accepted normalized observation preserves:

- tenant, workspace, resource scope, and facility;
- system and optional asset/equipment;
- connection, external signal, external tag, mapping revision, and canonical signal identity;
- original value and unit, normalized numeric value and canonical unit;
- raw source timestamp, source timezone/offset, normalized UTC observation time, and UTC ingestion time;
- reported and normalized quality, ingestion disposition, analysis eligibility, and reason codes;
- provider event identity where supplied, source-record digest, bounded source metadata, conversion/version, and timestamp-normalization version.

Raw full connector payloads are not persisted as an operational convenience. Evidence retains bounded lineage and exact identifiers needed to trace a result without copying credentials or sensitive connection configuration.

## Production provider boundary

Production and legacy connector registries are deliberately separate.

| Provider | Production state | Contract |
|---|---|---|
| `https_telemetry` | Implemented; production use additionally requires approved controlled egress | Public HTTPS origin on port 443, server-constructed `GET`, bounded validation/discovery/incremental/backfill/health |
| `historian_template` | Boundary implemented; unavailable until a reviewed template and executor are registered by server startup | Server-owned template and network profile, bounded typed parameters, no browser SQL/DSN/path/host |

The legacy `csv`, `rest`, and `database` connectors are local historical/manual compatibility adapters. They are not eligible providers for recurring production telemetry. Every `/api/connectors/*` compatibility route, including descriptors, test, upload/ingest, and global health, is tombstoned before request-body parsing in staging and production. The older unscoped `/api/telemetry/*` and `/api/live-analysis/*` SQLite seams are likewise tombstoned in shared environments; they cannot ingest, enumerate mappings/health, or create analysis by caller-supplied system ID. MQTT, OPC UA, BACnet, Modbus, and other placeholders are unavailable and expose no control path.

All production providers are retrieval-only. The connector interface has no setpoint, command, acknowledgement, write, actuator, start/stop, SQL-mutation, or arbitrary request method. The HTTPS adapter enforces:

- HTTPS only, port 443, no userinfo or fragments;
- `GET` only, no redirects, no environment proxy inheritance, and TLS verification;
- rejection of localhost, loopback, private, link-local, multicast, reserved, unspecified, and metadata-adjacent destinations for every resolved A/AAAA address;
- DNS authorization before each attempt and an authorized address pinned to the socket while preserving the original host and TLS SNI;
- same-origin, relative, bounded pagination only;
- bounded timeout, pages, records, response bytes, query fields, retries, backoff, and `Retry-After`;
- allow-listed field mappings and server-constructed authentication headers.

Application SSRF validation is one layer. Production enablement also requires a controlled egress route or proxy/firewall policy. Private customer sources require a separately designed and approved VPN, Transit Gateway, PrivateLink, site-agent, or equivalent network profile. Do not weaken the public connector to admit RFC1918 destinations.

## Credentials

Credential values are submitted once to the dedicated endpoint and represented to the browser only by `credentials_configured`, a version marker, and update time. Public connection, signal, error, audit, evidence, and health models contain no secret contents, ARN, internal reference, or binding identifier.

The production implementation uses AWS Secrets Manager with names under:

```text
neraium/<environment>/telemetry-connections/scope-<opaque-hash>/connection-<opaque-hash>
```

Ownership is revalidated using all of these tags before binding or resolution:

- `neraium:managed-by=telemetry-connections`
- `neraium:resource-scope-id=<server-derived-resource-scope>`
- `neraium:connection-id=<connection-id>`

Dynamic secret creation/update is disabled by default. There are two safe rollout choices:

1. approve scoped create/update IAM and set `NERAIUM_TELEMETRY_DYNAMIC_SECRET_WRITES=true`; or
2. keep it false and add/use a server-owned operations workflow that constructs `TrustedPreprovisionedSecretBinding` after checking the expected secret version and ownership tags.

The browser never supplies a secret reference. There is no plaintext database fallback. Secret values must never be placed in task environment arrays, logs, error payloads, evidence, or audit detail.

## Connection onboarding and authorization

The Data Connections workspace progressively discloses the customer workflow:

1. Choose an available retrieval-only provider.
2. Enter allow-listed connection metadata.
3. submit credentials one way.
4. Validate reachability and authentication.
5. Discover source tags.
6. Define/select a system and intentionally map signals/assets.
7. Review units, timezone, cadence, quality, and system coverage.
8. Prepare reference history through bounded backfill where supported.
9. Enable continued ingestion and inspect health, runs, and safe errors.

Server roles are authoritative:

| Action | Minimum role |
|---|---|
| List/read connections, providers, concepts, signals, runs, errors, and health | Authenticated facility member |
| Validate, discover, map, request retry, and start bounded backfill | Operator |
| Create/update/archive connection, update credentials, enable/disable | Administrator |
| Mutate historical import state in production | Administrator compatibility permission |

UI hiding is not authorization. Every API lookup is facility-scoped before mutation. State is cleared when the selected workspace changes so stale frontend state cannot authorize or display another facility.

## Discovery, mapping, units, time, and quality

Discovery registers all source tags as disabled and `unmapped`. A source tag is never analyzed until an authorized mapping identifies the facility, system, optional asset, canonical concept, source unit, source timezone, expected cadence when known, revision, actor, and provenance. Tag names and similarity may support a visibly marked suggestion, but never establish semantic authority without confirmation.

The v1 unit contract is explicit and versioned as `neraium.telemetry.units/v1`. It supports deliberate conversions within compatible dimensions, including °F/°C, psi/kPa, GPM/L/s, kW/W, and percent/fraction. Original values and units remain in lineage. Unknown units, unknown canonical targets, incompatible dimensions, and non-finite values are rejected or quarantined; they are never guessed.

The timestamp contract is versioned as `neraium.telemetry.timestamps/v1`. It preserves the source text and offset, accepts aware timestamps directly, and requires an IANA source timezone for a naive wall time. Ambiguous or nonexistent DST wall times, invalid zones, unparsable values, and timestamps more than the configured future tolerance are rejected. Duplicate instants are deduplicated. Valid older instants are preserved as out-of-order observations and marked accordingly.

Only good, explicitly mapped, enabled observations are analysis-eligible. Reported stale, missing, invalid, unknown-quality, mapping-required, or unit/time-invalid records remain visible as quality/rejection evidence and cannot silently enter SII.

## Durable ingestion and backfill

Recurring ingestion is server-side in the worker role. The production path is:

```text
Provider page
  -> raw observation validation
  -> mapping snapshot resolution
  -> unit normalization
  -> timestamp/order normalization
  -> quality decision
  -> atomic canonical observation + rejection persistence
  -> checkpoint compare-and-swap
  -> canonical analysis eligibility
  -> source-neutral system window
  -> SII exactly once
```

The PostgreSQL repository claims one due connection with a transactional lease. A run loads an immutable scoped connection/mapping snapshot, processes one bounded provider page, and atomically persists accepted observations, rejections, cumulative counters, and the next checkpoint. Checkpoints advance only with durable page writes. Continuations retain the run and cursor; retries are bounded with full jitter and provider `Retry-After`; expired leases and stale analysis claims can be recovered. Deduplication uses scoped provider-event/source-record identities. One bad tag becomes a rejection and does not discard valid siblings.

Backfill is a durable run mode, not a separate ingestion implementation. API requests must use timezone-aware UTC bounds, are currently capped at 31 days per request, require an enabled provider with bounded-backfill capability, and refuse overlapping active backfills. Work resumes from the persisted backfill checkpoint and passes through the same mapping, normalization, quality, persistence, and analysis seam as incremental telemetry. Larger reference histories must be divided into approved bounded ranges and monitored between ranges.

## One SII handoff

The source-neutral `CanonicalAnalysisWindow` carries server-attested facility/system identity, canonical signal columns, UTC rows, quality/coverage, ingestion report, and observation lineage. It rejects vendor fields, stale authority, duplicate canonical pivots, insufficient coverage, and unbounded windows.

`telemetry_analysis_service` deterministically identifies and durably claims an analysis window, calls the existing authoritative `evaluate_sii(...)` orchestration exactly once, and atomically records terminal result/evidence/finding metadata plus exact observation links. Incremental telemetry, backfill, and any future approved provider converge here. Connected telemetry is never converted into synthetic CSV or assigned an upload identity, and connector-specific intelligence logic is forbidden.

An ineligible or insufficient window is a valid no-finding outcome. It records the reason, such as missing mapped coverage, insufficient time coverage, stale quality, or unavailable authority, without inventing a result.

## Health, metrics, logs, and audit

Connection health is multidimensional:

| Facet | Meaning |
|---|---|
| Reachability | A recent endpoint/provider probe completed |
| Authentication | The source accepted the current credential |
| Telemetry freshness | Canonical telemetry is arriving within cadence-derived windows |
| Mapping completeness | Discovered tags have intentional mappings |
| Data quality | Mapped signals are current and accepted |
| Worker/checkpoint | Durable ingestion progress is current |

The aggregate is deterministic, but operators should diagnose the facets. `connected` after validation does not mean telemetry is arriving. An enabled source with no telemetry or stale checkpoints is degraded/unhealthy even when authentication remains valid.

Use connection/run/health records and structured events to monitor:

- healthy/degraded/error connection counts;
- `last_attempt_at`, `last_success_at`, `last_telemetry_at`, ingestion latency, and next attempt;
- observations received, accepted, rejected, duplicate, and out-of-order;
- discovered/mapped/healthy/stale signal counts and mapping failures;
- retry counts, safe error codes, partial runs, lease recovery, and worker heartbeat/failures;
- analysis status and ineligibility reason.

Relevant structured events include `worker_telemetry_result`, `telemetry_scheduler_iteration_failed`, `telemetry_ingestion_run_failed`, `telemetry_worker_heartbeat_publish_failed`, `telemetry_schema_readiness_failure`, `telemetry_runtime_configuration_failed`, and secret-store failure events. Never log raw telemetry payloads, full connection URLs with query strings, headers, DSNs, internal secret references, secret values, or connector exception text.

Connection creation and its audit event share one PostgreSQL transaction. Secret binding/version persistence and its audit event also commit atomically. Because a Secrets Manager write necessarily precedes that database transaction, a database failure emits the sanitized `telemetry_secret_binding_reconciliation_required` event with connection/scope identity but no secret reference or value; operations must reconcile the owned secret tags/version and scoped binding before retrying.

The global worker reconstructs and validates the complete canonical scope before assigning a lease or ingestion run. A malformed legacy/global row is disabled with `telemetry_scope_invalid`, emits `telemetry_legacy_scope_quarantined`, and is skipped so it cannot inherit scope or starve valid tenant connections.

Audit events cover connection creation/update/archive, credential binding changes, validation results, mapping changes, enable/disable, retry requests, and backfill start/completion/failure. Each event carries actor, tenant/facility scope, connection, action, and UTC timestamp. There is intentionally no audit event per telemetry sample.

## Operations quick checks

Before enabling a connection:

- confirm the explicit facility and system authority exists;
- confirm the selected provider is reported available by `GET /api/data-connections/providers`;
- verify controlled egress and Secrets Manager permissions from both relevant task roles;
- validate and inspect reachability/authentication separately;
- discover signals and map only the signals approved for the system model;
- confirm every enabled mapping has a compatible unit and explicit timezone/cadence;
- review coverage and request a bounded backfill if reference history is needed;
- enable only after the telemetry worker heartbeat and schema readiness are healthy.

If telemetry is stale, inspect in order: worker heartbeat, active/expired lease, last attempt and safe error code, checkpoint age, provider reachability, authentication/version, then source cadence. Do not repeatedly validate credentials as a substitute for checking arrival and checkpoint progress.

If rejections rise, group by stable reason and signal. Correct a mapping/unit/time contract, then request a bounded retry or backfill. Do not delete canonical observations or reset checkpoints by hand.

## Deployment prerequisites and approval boundary

No item in this section is evidence that production infrastructure already exists. Before deployment, an authorized operator must verify and separately approve all of the following:

- a shared PostgreSQL database on a repository-supported version, reachable by API and worker, with TLS required, the additive telemetry migrations applied in order, and least-privilege application/migration identities;
- task-definition secret injection for `NERAIUM_TELEMETRY_DATABASE_URL`; never place the DSN in a plain environment entry or log;
- API/worker Secrets Manager permissions scoped to `neraium/<environment>/telemetry-connections/*`, the ownership-tag policy, and KMS decrypt access when a customer-managed key is used;
- a decision between approved dynamic secret writes and a server-owned pre-provisioned binding workflow;
- controlled HTTPS/443 egress that independently blocks private/metadata networks and permits only approved public source destinations;
- a dedicated worker service using `NERAIUM_PROCESS_ROLE=worker`, background workers enabled, a stable instance count/capacity, and no legacy API poller;
- `NERAIUM_TELEMETRY_DATABASE_URL`, `NERAIUM_TELEMETRY_SECRET_REGION`, `NERAIUM_TELEMETRY_CONTROLLED_EGRESS_ENABLED=true`, scheduler timing, lease duration, and heartbeat interval on the appropriate task definitions;
- `NERAIUM_TELEMETRY_LEGACY_COMPAT=false` in shared environments (production code also refuses this mode there);
- CloudWatch collection/alarms for telemetry worker absence, repeated scheduler failures, stale ingestion beyond cadence, retry storms, rejection spikes, and secret/egress failures;
- an explicit historian startup registry and reviewed executor before advertising `historian_template` as available;
- a retention/capacity decision for canonical observations and rejections before broad rollout.

The exact migration and deployment sequence, rollback posture, and post-deploy checks are in [Database migrations](database-migrations.md#production-telemetry-schema) and [AWS Deployment Preparation](AWS_DEPLOYMENT.md#production-telemetry-connections-separate-approval-required). Operational response is in [Production Operations Guide](OPERATIONS.md#production-telemetry-operations).
