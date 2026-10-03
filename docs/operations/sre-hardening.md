# Production V2 operations: first customer

Baseline: release `94007976e6a854780541e29681035890ed074bfd`, tag `neraium-1.0-production-v2-2026-10-02`; ECS `neraium-prod-api:338`, `neraium-prod-worker:332`; region `us-east-2`. Only synthetic traffic is permitted for drills. This document is an operator checklist, not a change to analytical behavior.

## SLIs and initial SLOs

Use UTC calendar months. ALB metrics include every request reaching the target group, including health probes and rejected requests; report that traffic mix alongside API rates. Exclude invalid input and authorization rejects from telemetry workflow failure counts. A month with no attempted work has no workflow success-rate result; it is not 100%. These are initial operational objectives, not historical achievements. CloudWatch ALB and ECS signals are externally collected. New application log events are emitted only after the code in this phase is deployed.

| SLI (eligible denominator) | Source and measurement | Initial SLO |
|---|---|---|
| API availability | ALB `HealthyHostCount` at least 1, plus `HTTPCode_ELB_5XX_Count`/`RequestCount`; successful `/api/health` probe | 99.5% of one-minute periods have a healthy target; 99% of eligible requests avoid ALB 5xx |
| API latency | ALB `TargetResponseTime` p95, minutes with requests only | p95 under 2 seconds in 95% of sampled minutes |
| Telemetry ingestion | PostgreSQL `telemetry.ingestion_runs` completed vs terminal failed; worker `telemetry_ingestion_run_completed` and `telemetry_ingestion_page_failed` events | 99% of terminal scheduled runs complete; retry-scheduled runs are not terminal failures |
| Connector executor | EC2 `StatusCheckFailed`, plus scheduler failure `error_code` prefixed `connector_executor_`; `telemetry_connector_fetch_completed` worker event | EC2 checks pass in 99.5% of minutes; 98% of attempted fetches succeed, excluding invalid customer configuration |
| Worker health | ECS `RunningTaskCount` and S3 `infrastructure/worker-heartbeat.json` age | Task running in 99.5% of minutes; heartbeat under 2 minutes while scheduled |
| Analysis execution | `telemetry_analysis_completed` / `telemetry_analysis_failed` worker events, with PostgreSQL analysis status as durable cross-check | 98% of eligible attempted analyses complete; ineligible windows excluded |
| V2 persistence | `telemetry_v2_persistence_completed` / `telemetry_v2_persistence_failed` worker events; V2 execution and lineage tables | 99.5% of attempted V2 persistence operations complete |
| Result retrieval | `telemetry_v2_retrieval_completed` / `telemetry_v2_retrieval_failed` events for V2 list/detail; ordinary not-found excluded; authenticated synthetic list/detail probe | 99.5% of eligible attempted verified reads succeed; failures before route retrieval (including scope lookup) require separate synthetic probe coverage |
| Database connectivity | `/api/ready` DB checks, RDS `DatabaseConnections`/availability, `readiness_dependency_failed` event | 99.5% of one-minute readiness probes pass; no scheduled customer work while unavailable |
| Queue/scheduler lag | Admin `/api/ready?verbose=true` `queue_operational_metrics.oldest_pending_age_seconds`; worker `telemetry_scheduler_claim_lag` measures age at claim | Upload pending age under 10 minutes and claimed telemetry work lag under 10 minutes for 95% of sampled active-work minutes; unclaimed telemetry backlog remains unmeasured |

Manual denominator review: query scoped operational metadata only, never customer payloads. A successful API health probe is not proof that authentication, ingestion, or persistence works. Avoid treating low-volume, missing, or retrying activity as a success rate.

## Alerts and response

CloudWatch alarms route to SNS `neraium-prod-infrastructure-alerts`. Verify at least one **confirmed** operator subscription before onboarding: `aws sns list-subscriptions-by-topic --topic-arn arn:aws:sns:us-east-2:680779862188:neraium-prod-infrastructure-alerts --region us-east-2`. `PendingConfirmation` is not delivery. ALARM and OK actions use the same topic. All thresholds below are consecutive one-minute periods unless noted. The deployment owner is the operator running the GitHub deployment; the same person is the primary incident contact until an actual on-call roster exists. If they cannot respond, escalate directly to the repository/production AWS account owner. Do not claim 24-hour paging until an operator confirms it.

| Alarm / what failed | Severity; signal | Likely impact; first diagnostic action; runbook |
|---|---|---|
| `api-no-healthy-alb-targets`, API unavailable | SEV1; zero healthy targets 5/5 | API unavailable; inspect ECS events and ALB target health; [API](#api-unavailable) |
| `api-tasks-unavailable`, API process absent | SEV1; running tasks below 1 for 3/3 | API unavailable; inspect ECS task stop reason; [API](#api-unavailable) |
| `worker-tasks-unavailable`, worker absent | SEV2; running tasks below 1 for 3/3 | processing delayed; inspect ECS events and worker logs; [worker](#worker-unavailable) |
| `connector-executor-status-failed`, EC2 host impaired | SEV2; status check failed 2/3 | scheduled fetches delayed; inspect EC2 status and executor container; [executor](#connector-executor-unavailable) |
| `api-slow`, abnormal latency | SEV2; ALB target p95 >2s 5/5 | slow requests; inspect ECS CPU/memory and RDS load; [API](#api-unavailable) |
| `api-target-5xx`, API errors | SEV2; at least five target 5xx in 3/5 | requests fail; inspect API logs and dependencies; [API](#api-unavailable) |
| `auth-database-failures`, DB readiness | SEV1; three failure minutes in 5 | sign-in/result work fails; inspect RDS status and ready endpoint; [database](#database-unavailable) |
| `credential-refresh-failures`, rotating credentials | SEV2; three failure minutes in 5 | DB access may expire; inspect secret rotation metadata; [secrets](#credential-or-secret-failure) |
| `secrets-access-failures`, Secrets Manager | SEV2; three failure minutes in 5 | credential refresh may fail; inspect IAM and secret status; [secrets](#credential-or-secret-failure) |
| `worker-iteration-failures`, upload worker | SEV2; three failure minutes in 5 | queued uploads delayed; inspect worker logs; [worker](#worker-unavailable) |
| `telemetry-scheduler-failures`, scheduler loop | SEV2; three failure minutes in 5 | scheduled ingestion delayed; inspect worker logs/DB; [worker](#worker-unavailable) |
| `telemetry-scheduler-lag-high`, overdue claimed work | SEV2; claimed work >10 minutes late in three of five minutes | ingestion delayed; inspect worker count and backlog; [ingestion](#telemetry-ingestion-failing) |
| `telemetry-ingestion-failures`, repeated page failure | SEV2; three failure minutes in 5 | telemetry delayed; inspect sanitized `error_code`; [ingestion](#telemetry-ingestion-failing) |
| `connector-executor-repeated-failures`, repeated executor errors | SEV2; three failure minutes in 5 | telemetry delayed; inspect EC2 status and sanitized `error_code`; [executor](#connector-executor-unavailable) |
| `v2-analysis-failures`, execution failures | SEV2; three failure minutes in 5 | V2 results delayed; inspect worker event and DB; [V2](#v2-execution-failing) |
| `v2-persistence-failures`, durable write/readback | SEV2; three failure minutes in 5 | results may be unavailable; inspect RDS and worker logs; [result](#result-persistence-or-retrieval-failing) |
| `v2-retrieval-failures`, verified readback | SEV2; three failure minutes in 5 | saved result inaccessible; inspect API event and RDS; [result](#result-persistence-or-retrieval-failing) |

EC2 status cannot prove the executor HTTP process is healthy. The `connector_executor_` scheduler error code is the application-level signal; an independent synthetic executor request is still needed for silent outage detection. Log-based alarms use 3/5 to suppress one-off transient retries. Customer-configured connector errors require diagnosis before any intervention.

## Common first checks

```bash
aws ecs describe-services --cluster neraium-prod-cluster --services neraium-prod-api-service neraium-prod-worker-service --region us-east-2 --query 'services[].[serviceName,desiredCount,runningCount,taskDefinition,events[0].message]'
aws cloudwatch describe-alarms --alarm-name-prefix neraium-prod- --region us-east-2 --query 'MetricAlarms[].[AlarmName,StateValue,StateReason]'
aws logs tail /ecs/neraium-prod-api --since 15m --region us-east-2
aws logs tail /ecs/neraium-prod-worker --since 15m --region us-east-2
curl -fsS https://app.neraium.com/api/health
curl -fsS https://app.neraium.com/api/ready
```

Do not paste raw customer records, tokens, credentials, or unsanitized request bodies into incident notes.

### API unavailable

Check ALB healthy targets, ECS service events/task stop reason, then `/api/health` and `/api/ready`. If a new rollout caused the failure, follow [rollback](#rollback). If readiness alone fails, inspect its dependency logs before restarting tasks.

### Worker unavailable

Inspect `neraium-prod-worker-service` desired/running count and `/ecs/neraium-prod-worker` events. Check admin `/api/ready?verbose=true` queue age and the worker heartbeat in the shared upload-state S3 bucket. Restart via ECS only after capturing stop reason; verify a synthetic queued job completes.

### Connector executor unavailable

Run `aws ec2 describe-instance-status --instance-ids i-081d0aba82dba64e7 --include-all-instances --region us-east-2`. Check instance system and instance status and the `neraium-connector-executor` container via approved SSM access. Inspect worker `connector_executor_` error codes. Do not remove executor isolation or controlled egress. Confirm recovery with a synthetic connection only.

### Telemetry ingestion failing

Filter worker logs for `telemetry_ingestion_page_failed`; review `error_code`, retryable state, and connection ID. Check executor and RDS first. Inspect ingestion-run status and checkpoint through the authenticated operator API. Do not advance a checkpoint manually; let the existing retry/lease path recover, then verify a synthetic completed run.

### Database unavailable

Run `aws rds describe-db-instances --db-instance-identifier neraium-prod-postgres --region us-east-2 --query 'DBInstances[0].[DBInstanceStatus,LatestRestorableTime]'`. Inspect RDS events, CloudWatch DB connections/CPU/free storage, API readiness, and credential refresh logs. Do not change production schema or restore over the live instance. Escalate SEV1 if authentication or result retrieval is affected.

### V2 execution failing

Filter worker logs for `telemetry_analysis_failed` and `telemetry_analysis_handoff_failed`. Check the synthetic ingestion run ID and persisted status. Inspect executor, database, and scheduler health. Retain the failed run and evidence; retry through the existing scheduler path only after the dependency recovers. Do not alter analytical thresholds or replay customer data.

### Result persistence or retrieval failing

Filter worker logs for `telemetry_v2_persistence_failed`, API logs for `telemetry_v2_retrieval_failed`, and RDS events. Use authenticated synthetic list and detail requests and verify `lineage_verified=true`. A not-found response for an unknown ID is expected; never bypass scope or lineage checks. Escalate if a previously returned synthetic result becomes unreadable.

### Deployment failure

Record GitHub Actions run URL, image digest, task definition ARNs, migration task exit code, ECS events, target health, and smoke output. Stop subsequent deployments. If the new revision is serving and unhealthy, use the rollback decision below. A failed migration must be investigated before any task rollback.

### Rollback

Decision point: roll back both API and worker if either loses readiness or the certified synthetic workflow regresses for 5 minutes after rollout. Previous pair currently available: `neraium-prod-api:337` and `neraium-prod-worker:331`; current certified pair: `:338` and `:332`. Recheck task-definition image digests and migration compatibility before execution. Snapshot current service task-definition ARNs first. Rollback changes code only; **never** roll back migrations or overwrite RDS. Migration 010 drops a concept uniqueness index and adds an immutable mapping trigger; old-code write compatibility after this migration is **unproven**. Treat the previous pair as an emergency read-path candidate only until an isolated compatibility drill confirms the certified workflow. Do not run the following commands solely on the assumption that a previous revision is safe.

```bash
aws ecs update-service --cluster neraium-prod-cluster --service neraium-prod-api-service --task-definition neraium-prod-api:337 --region us-east-2
aws ecs update-service --cluster neraium-prod-cluster --service neraium-prod-worker-service --task-definition neraium-prod-worker:331 --region us-east-2
aws ecs wait services-stable --cluster neraium-prod-cluster --services neraium-prod-api-service neraium-prod-worker-service --region us-east-2
curl -fsS https://app.neraium.com/api/ready
```

To restore certified revisions, update the two services to `neraium-prod-api:338` and `neraium-prod-worker:332`, wait for stability, repeat readiness and synthetic list/detail. These commands are for an authorized incident or controlled drill; they have **not** been run in this phase.

### Credential or secret failure

Check `neraium-prod-credential-refresh-failures` and `neraium-prod-secrets-access-failures`, then `aws secretsmanager describe-secret --secret-id neraium/prod/connector-executor-auth --region us-east-2` or the RDS managed secret ARN from `describe-db-instances`. Inspect rotation status and task IAM errors. Never print secret values or place credentials in task definitions. Restore IAM/rotation access, then verify readiness and a synthetic connector fetch.

## Backups and isolated restore

On 2026-10-03, `neraium-prod-postgres` was `available`, encrypted, deletion protected, with 7-day automated retention and latest restorable time present. Eight available encrypted automated snapshots were listed through `rds:neraium-prod-postgres-2026-10-02-07-40`. This proves backup configuration and snapshot existence, **not** successful restoration.

Restore drill procedure: choose a current automated snapshot; restore to a uniquely named temporary RDS instance in the production VPC's isolated subnet group with a **new** security group that permits only an approved temporary inspection task. Use the actual snapshot ID from `describe-db-snapshots`, then run:

```bash
aws rds restore-db-instance-from-db-snapshot --db-instance-identifier neraium-restore-drill-20261003 --db-snapshot-identifier rds:neraium-prod-postgres-2026-10-02-07-40 --db-subnet-group-name default-vpc-046a8eee54c6988ae --vpc-security-group-ids "$ISOLATED_INSPECTION_SG_ID" --no-publicly-accessible --region us-east-2
aws rds wait db-instance-available --db-instance-identifier neraium-restore-drill-20261003 --region us-east-2
```

Use a temporary ECS/SSM session with read-only DB credentials to run `SELECT migration_id FROM telemetry.schema_migrations ORDER BY migration_id` and inspect `information_schema.tables` for `telemetry.ingestion_runs`, `telemetry.relationship_lineage_artifacts_v2`, and `telemetry.endpoint_analysis_executions_v2`. Verify IDs 002–010 without selecting customer rows. Capture only schema/ledger evidence. After confirming the temporary identifier, run `aws rds delete-db-instance --db-instance-identifier neraium-restore-drill-20261003 --skip-final-snapshot --region us-east-2`, wait for deletion, then remove the temporary inspection security group. A restore drill was not run in this phase; no temporary database was created. Do not substitute the live database identifier into these commands.

## Capacity and failure recovery baseline

The certified Production V2 synthetic workflow proves one end-to-end run, persistence, retrieval, and restart retrieval. The historical `docs/performance/production-processing-2026/raw/end_to_end-10000-1.output.json.gz` artifact reports **10,000 rows, 4 columns, 11.51 seconds processing time** for the earlier upload path. That is one measured worker processing sample, not API concurrency, scheduled ingestion, V2 throughput, or a sustained rate. Current ALB p95 and RDS metrics are live operational signals, not load limits. Safe working limit for first customer: one controlled synthetic acceptance flow at a time, monitor queue age and p95, and stop enrollment if either alert persists. API concurrency, ingestion pages/minute, worker jobs/minute, V2 windows/minute, and DB writes/minute remain unknown; establish them in an isolated environment before raising volume.

No intentional production dependency outage or ECS restart was performed. Existing unit/integration tests cover fail-closed connector and persistence paths; a full recovery drill still needs an isolated test environment. Never stop the production DB or connector executor solely to test an alarm.

## Incident handling

SEV1: API/auth/database unavailable or verified persisted results inaccessible; deployment owner responds immediately and contacts the production AWS account owner. SEV2: sustained worker, connector, ingestion, analysis, persistence, or latency degradation; investigate in the same operating session and pause onboarding. SEV3: a single retry or monitoring data gap; review in the next operating session. Record UTC start/end, alarm history, service and task revisions, deployment run, sanitized request/run IDs, RDS/EC2 status, synthetic probe results, actions taken, and customer impact. After recovery, write a short review within two working days: timeline, cause, detection gap, remediation owner, and whether SLOs or runbooks need revision. Keep customer telemetry and secrets out of the review.
