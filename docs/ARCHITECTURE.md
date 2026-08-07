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

The operator workspace is organized around distinct product objects:

- **Systems** are operational equipment or processes discovered from telemetry behavior.
- **Datasets** are bounded telemetry collections imported for analysis.
- **Connectors** are configured read-only integrations with their own health state.
- **Analyses** are individual SII executions against datasets.
- **Insights** are operator-facing behavior changes that may warrant investigation.
- **Evidence** is the observed telemetry and comparison context supporting an insight.

The Operations Brief prioritizes current findings and discovered systems. Classification summaries expose data confidence, operating-mode match, persistence, and review priority without using red for unexplained systemic change. Findings and Investigations order the engineer view from observed change and classification rationale through context, timeline, evidence, checks, alternatives, and limitations. Shared frontend normalization keeps older saved findings readable without silently strengthening their classification. Data manages datasets, baseline imports, and connector availability. Analysis Details exposes analysis metadata and support diagnostics. Help & Status explains the product language and current service state. Administration provides governance records, user access, and session controls.

## Local Integration

During local development:

- Backend: `http://127.0.0.1:8010`
- Frontend: `http://127.0.0.1:3010`

Runtime configuration is centralized in `backend/app/core/config.py` and `frontend/src/config.js`. AWS deployment preparation is documented in `docs/AWS_DEPLOYMENT.md`.

## Product Language

`docs/PRODUCT_LANGUAGE.md` is the source of truth for Neraium and SII terminology, entity names, health states, severity, and sanitized operator-facing messages.
