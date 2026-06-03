# Phase 1 Pilot Readiness Checklist (Zero-Tolerance)

Status legend: `Implemented`, `Partial`, `Missing`

## Deployment & Infrastructure
- [x] Containerized deployment � **Implemented** (`Dockerfile`, `backend/Dockerfile`).
- [x] Reproducible AWS bootstrap/deploy automation - **Implemented/Partial** (AWS CLI bootstrap script + GitHub workflows; no Terraform state).
- [ ] Environment parity (dev/staging/prod identical) � **Partial** (documented targets, no enforced parity templates).
- [ ] Secrets management (Secrets Manager/Vault/Doppler) � **Partial** (`NERAIUM_API_TOKEN` env supported; no managed secret backend integration).
- [ ] Domain + SSL auto-renew � **Partial** (documented via ECS/Amplify; no repo automation).
- [ ] Reverse proxy/API gateway + rate limiting � **Partial** (deploy doc mentions ALB/ECS; no codified gateway/rate-limit config in repo).
- [x] Health checks � **Implemented/Partial** (`/api/health`, `/api/ready`; ready checks runtime DB/queue/inference path but no external DB/MQ yet).
- [x] Graceful shutdown � **Implemented** (FastAPI lifespan starts/stops poller + upload worker on shutdown).

## Data Pipeline & Processing
- [x] Telemetry ingestion API with validation/timeouts � **Implemented/Partial** (FastAPI + Pydantic models; API timeout handling in frontend helper; backend request-size caps not explicit).
- [x] Input schema enforcement � **Implemented** (strict parsing/validation paths in connectors + models).
- [ ] Time-series storage (ClickHouse/Timescale/Influx) � **Missing** (runtime storage is local runtime DB/files).
- [x] Ring buffer / streaming architecture � **Partial** (chunked ingestion + queue worker; explicit O(1) ring buffer guarantee not codified/documented).
- [x] Backpressure handling � **Partial** (queued jobs and polling controls; no explicit shed-load policy/limits documented).
- [x] Idempotent ingestion � **Partial** (job pipeline + history controls exist; formal idempotency keys/duplicate-write guardrails not fully specified).

## Core Algorithm & Detection
- [x] Deterministic inference � **Partial** (deterministic code paths, but no formal determinism contract tests across builds/hardware).
- [ ] Baseline persistence to object storage with versioning � **Missing** (local runtime persistence; no S3 versioned model store).
- [ ] State recovery without retraining from scratch � **Partial** (runtime state reload exists; durability across infra replacement depends on runtime volume setup).
- [ ] Sub-50ms inference path benchmarked in prod-like load � **Missing** (no benchmark artifact proving p50/p95 < 50ms).
- [x] Alert state machine hardened + restart-safe � **Partial** (state transitions present; explicit restart/idempotency transition test matrix incomplete).

## Security
- [x] API authentication for every endpoint � **Partial** (`require_api_access` on core routers; ensure all externally exposed routes remain protected by policy).
- [ ] Network isolation/private subnets � **Missing in repo** (deployment-level control not codified as IaC).
- [x] CSP + security headers � **Implemented/Partial** (CSP, HSTS, nosniff, frame/referrer headers added in middleware).
- [ ] Dependency scanning in CI � **Missing** (`pip-audit`/Snyk workflow not present).
- [ ] Read-only verification vs SCADA/BMS write paths � **Missing** formal audit artifact.

## Observability
- [x] Structured logging with trace/correlation IDs � **Partial** (`X-Request-Id` propagation; logging is present but not fully JSON-structured across all services).
- [ ] Application metrics (Prometheus/Datadog) � **Partial** (`/api/observability/summary` exists; no Prometheus/Datadog exporter/integration).
- [ ] Alerting on the alerter � **Missing** (no on-call alert rules/integration in repo).
- [ ] Log retention policy (30/90 days) � **Missing in repo** (ops policy/infrastructure config not codified).

## Minimum Work Plan To Reach Pilot Gate
1. Harden the AWS CLI bootstrap path for VPC/private subnets, ALB, ECS/Fargate, runtime storage, and DNS/TLS so production changes remain reproducible without Terraform.
2. Introduce managed secrets integration and remove direct env-secret assumptions from deployment docs.
3. Add durable model/baseline persistence to S3 with versioned keys and startup recovery path.
4. Add ingestion hard limits: max payload size, queue depth thresholds, and explicit load-shed responses.
5. Add CI security lane: `pip-audit` + image scanning + failing policy on high/critical CVEs.
6. Add Prometheus metrics endpoint and alert rules (latency, error rate, queue backlog, inference time, service-down).
7. Produce a formal SCADA/BMS read-only code audit report with path-level evidence.
8. Add performance benchmark suite proving sub-50ms inference under production-like load.
