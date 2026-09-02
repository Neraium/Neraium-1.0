# Infrastructure Manifest

> Generated: 2026-09-02
> Project: Neraium 1.0

## Current Systems

### Production PostgreSQL — authentication and telemetry authority

- **Type**: database
- **Product**: Amazon RDS for PostgreSQL (`neraium-prod-postgres`, database `postgres`)
- **Config**: `.github/workflows/deploy-backend.yml`, `backend/app/services/auth_store.py`, `backend/app/services/telemetry_runtime.py`
- **Connection**: auth resolves the rotating RDS master secret at runtime; telemetry accepts a PostgreSQL DSN injected as an ECS secret
- **Used by**: API authentication; additive facility-scoped `telemetry` schema shared by API and worker

### AWS Secrets Manager — credentials

- **Type**: secret storage
- **Config**: `scripts/bootstrap-production-aws.sh`, `backend/app/services/telemetry_secrets.py`
- **Connection**: ECS secret injection for DSNs; task-role SDK access to scoped connector secrets
- **Used by**: ECS execution role, auth backend, telemetry API and worker

### Amazon ECS/Fargate — application runtime

- **Type**: container orchestration
- **Config**: `.github/workflows/deploy-backend.yml`
- **Connection**: split API and worker services plus a one-off telemetry migration task
- **Used by**: backend API, upload worker, telemetry scheduler

### Amazon S3 — upload state

- **Type**: object storage
- **Config**: `scripts/bootstrap-production-aws.sh`
- **Connection**: AWS SDK through the application task role
- **Used by**: split-process upload queue and source objects

### CloudWatch and SNS — operations

- **Type**: monitoring and notifications
- **Config**: `scripts/configure-production-monitoring.sh`
- **Connection**: ECS logs, metrics, alarms, and scoped SNS publication
- **Used by**: API and worker production health monitoring

## Connection Graph

```text
Browser -> CloudFront/ALB -> ECS API -------> RDS PostgreSQL
                              |                    `telemetry` schema
                              +-> Secrets Manager
ECS worker ------------------> RDS PostgreSQL
    |                         -> Secrets Manager
    +-> S3
One-off migration task ------> RDS PostgreSQL (migrations 002/003/004)
API/worker -------------------> CloudWatch -> SNS
```

## Access Patterns

- API and worker coordinate telemetry leases, observations, health, and analysis through the same PostgreSQL schema.
- Connector credentials are resolved server-side; values and secret references are not returned to browsers.
- Production HTTPS telemetry is fail-closed until an independent controlled-egress boundary is verified.

## Opportunities

### Complete production telemetry prerequisites

- **Signal**: production currently returns `telemetry_database_not_configured`.
- **System**: existing RDS instance with dedicated migration and application identities.
- **Impact**: enables the facility-scoped registry and scheduler without adding another database.
- **Effort**: medium

## Multi-Repo Considerations

None identified. Production infrastructure and application deployment contracts are maintained in this repository.
