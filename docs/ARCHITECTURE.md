# Neraium Architecture

## Current Scope

Neraium is a full-stack platform for commercial water-system operators. Systemic Infrastructure Intelligence (SII) is the intelligence Neraium applies to infrastructure telemetry.

Production analytical authority is defined in [SII authority boundaries](SII_AUTHORITY_BOUNDARIES.md). Structural-cognition research packages, static standards/reference assets, and future cross-system capabilities do not participate in the normal customer upload result merely because implementations exist in the repository.

- A FastAPI backend exposes authenticated API endpoints under `/api`.
- A Vite React frontend provides operator, administration, and evidence-review workspaces.
- Role-based access distinguishes viewers, operators, and administrators.
- Shared PostgreSQL stores scoped production telemetry connections, mappings, observations, leases, checkpoints, analysis windows, and lineage. Compatibility runtime persistence continues to store historical-import jobs and related state.
- The production connection boundary supports hardened read-only HTTPS retrieval and a fail-closed server-owned historian template boundary. CSV, legacy REST/database, global SQLite telemetry, and legacy live-analysis adapters are local historical/manual compatibility paths; their API routers return `410` in shared environments and are not recurring production telemetry providers.

## Backend

The backend lives in `backend/app`.

```text
backend/app/main.py          FastAPI app factory, security middleware, and router registration
backend/app/routers/         Authenticated routes grouped by product workflow
backend/app/services/        Dataset ingestion, SII analysis, evidence, persistence, and connector services
backend/app/engine/          Deterministic Systemic Infrastructure Intelligence engine
backend/requirements.txt     Python runtime and test dependencies
```

Major API workflows include authentication and session management, facility/system setup, Data Connections onboarding, telemetry discovery and mapping, connection health, findings, investigations, evidence review/export, administration, observability, and behavior replay. Historical import remains an admin-gated compatibility workflow rather than normal production onboarding.

### Production telemetry authority

Production telemetry follows the server-authoritative hierarchy `Tenant -> Facility -> System -> Asset/Equipment -> Signal`. Signals are evidence inputs to a defined physical system. They are not independently monitored product objects. Every connection, signal, mapping, run, checkpoint, observation, health record, error, audit event, analysis window, and evidence link carries the authenticated facility resource scope.

The worker retrieves one bounded provider page under a PostgreSQL lease, resolves an approved mapping snapshot, normalizes unit/time/quality, atomically persists accepted observations and per-record rejections with a checkpoint revision, then projects eligible observations into one source-neutral canonical system window. That window invokes the existing authoritative SII orchestration exactly once and preserves exact observation lineage. Connector type never selects a different intelligence implementation.

See [Production Telemetry Connections](TELEMETRY_CONNECTIONS.md) for the entity, provider, authorization, ingestion, health, and deployment contracts.

Historical imports pass through the versioned ingestion and trust boundary in [Historical Data Ingestion & Trust v1](HISTORICAL_DATA_INGESTION_TRUST_V1.md). Received bytes are retained as immutable, content-addressed raw artifacts in the existing tenant/workspace storage scope. Parsing, mapping, unit conversion, exclusions, review decisions, and canonical rows are separate derived records. Only included canonical values enter the bounded analysis workflow. SII compares behavior windows and system relationships. It does not claim root cause, predict failure, or control equipment.

Behavioral baseline index entries persist their canonical model, dataset, and job references together. Dataset-to-baseline recovery therefore resolves the newest matching result directly from the index; model-record scanning remains only as a compatibility path for indexes created by older releases.

### Engineering finding certainty

The SII engine remains unchanged and supplies relationship, persistence, and corroboration evidence. The upload and explanation services add four inspectable certainty layers:

1. `operating_modes.py` compares the relationship engine's baseline and recent periods using explicit state, staging, load, schedule, environmental, setpoint, and event telemetry. Numeric context bands are learned from the uploaded dataset; they are not universal engineering thresholds.
2. `sensor_health.py` extends existing profiles, normalization integrity, ingestion counts, timestamp checks, and confidence caps into qualitative per-signal health and `high`, `limited`, or `low` data confidence.
3. `finding_classification.py` deterministically assigns `known_operational_change`, `possible_instrumentation_issue`, `unexplained_systemic_change`, or `insufficient_evidence`.
4. `analysis_explanations.py` applies classification-specific language and preserves the supporting mode, quality, persistence, relationship, timeline, and uncertainty evidence in the canonical analysis contract.
5. `investigation_guidance.py` structures the existing evidence-backed recommendation text, applies classification-specific ordering, and keeps every check editable and tied to a stated reason. It does not issue repair instructions or create a second diagnosis engine.

Low data confidence or insufficient relationship support prevents stronger claims. Weak or unavailable mode matching prevents an unexplained systemic classification. An unexplained systemic change means only that a persistent relationship changed under comparable recorded conditions; it is not a root-cause diagnosis, failure prediction, or emergency state.

Older saved analyses remain readable. Missing certainty fields are normalized to explicit unavailable/low evidence context while legacy display fields remain intact.

## Frontend

The frontend lives in `frontend`. Startup is split into a small authentication gateway and a deferred authenticated runtime. Signed-out and session-checking views do not load telemetry, analysis, or workspace state modules. Authenticated workspaces remain route-level lazy chunks, and the production performance budget verifies both the startup size and the deferred-runtime boundary.

The ongoing production workspace is organized around distinct product objects:

- **Facilities** are authorized customer workspaces containing defined physical systems.
- **Systems** are the unit of learned behavioral structure and ongoing evaluation.
- **Assets / Equipment** organize evidence inputs within a system without replacing system-level intelligence.
- **Data sources / Connections** are configured read-only telemetry integrations with multidimensional health.
- **Signals** are intentionally mapped evidence inputs to a system model.
- **Findings** are qualified system-level behavioral changes that deserve review.
- **Investigations** expose the technical evidence, limitations, context, and engineering checks behind a finding.
- **Evidence Records** preserve complete metrics, timestamps, identities, lineage, engine/version metadata, and audit context.

The production hierarchy is Results / Operations Brief -> Finding Review -> Investigation -> Evidence Record. The brief stays restrained; deeper evidence is disclosed on demand. Stable and insufficient-evidence states use calm system-level language and do not imply that every sensor is normal. Data Connections is the primary onboarding surface. Shared frontend normalization keeps older saved findings readable without silently strengthening their classification. Historical import is hidden from normal navigation and retained only for permission-gated compatibility. Help & Status explains the product language and service state. Administration provides governance records, user access, and session controls.

Frontend projections do not reconstruct research-only facade fields when they are absent. Investigation and Evidence Record retain the legitimate upload replay and qualified lineage; they do not expose heuristic causality, counterfactuals, synthetic fleet structures, ephemeral cognition memory, aggregate twin packaging, or failure-prediction aliases.

## Local Integration

During local development:

- Backend: `http://127.0.0.1:8010`
- Frontend: `http://127.0.0.1:3010`

Runtime configuration is centralized in `backend/app/core/config.py` and `frontend/src/config.js`. AWS deployment preparation is documented in `docs/AWS_DEPLOYMENT.md`.

## Product Language

`docs/PRODUCT_LANGUAGE.md` is the source of truth for Neraium and SII terminology, entity names, health states, severity, and sanitized operator-facing messages.
