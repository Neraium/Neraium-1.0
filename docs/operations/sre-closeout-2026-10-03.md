# Production SRE closeout evidence — 2026-10-03

Source commit: `74a542562f4569f9e72c58a0efcd96ff0801b2af`. Certified serving task definitions at the start of this check: API `neraium-prod-api:338`, worker `neraium-prod-worker:332`. All checks below used operational metadata or synthetic health probes; no customer telemetry was read.

## Alert delivery and deployment gates

- SNS topic `arn:aws:sns:us-east-2:680779862188:neraium-prod-infrastructure-alerts` had zero confirmed and zero pending subscriptions. No authorized operator destination was available to test. Alert delivery is unverified.
- The GitHub production deployment workflow's repository variables did not include `NERAIUM_TELEMETRY_EXECUTION_IDENTITY_VERSION`, `NERAIUM_TELEMETRY_CONTROLLED_EGRESS_ENABLED`, `NERAIUM_TELEMETRY_DATABASE_URL_SECRET_ARN`, or `NERAIUM_TELEMETRY_CONNECTOR_SECRET_ARN`. Its defaults are V1 identity and disabled controlled egress. The certified ECS definitions explicitly use V2 identity, controlled egress, and disabled dynamic secret writes. The workflow was not run because its current configuration cannot preserve those settings.
- The SRE code is not deployed. The existing CloudWatch alarms and metric filters are configured, but new application events cannot be verified until a safe rollout.
- Read-only CloudWatch verification found **17/17 alarms in OK**, with actions enabled and both ALARM and OK actions routed to the topic. The API log group has five metric filters and the worker log group has eleven. Topic subscription count remains zero, so alarm configuration is present but notification delivery fails the operational gate.

## Initial idle operational baseline

CloudWatch samples cover **2026-10-03 04:30:44–05:30:44 UTC**, 12 five-minute periods unless stated. These are observed idle resources, not load limits or maximum throughput. ECS utilization is percent of reserved task capacity. RDS values are instance metrics.

| Signal | Observed mean | Observed range |
|---|---:|---:|
| API CPU utilization | 1.64% | 1.23–2.05% |
| API memory utilization | 8.01% | 8.01% |
| Worker CPU utilization | 6.83% | 6.73–6.91% |
| Worker memory utilization | 3.08% | 3.08% |
| Connector executor EC2 CPU utilization | 1.03% | 0.96–1.06% |
| Connector executor EC2 status-check failures | 0 | 0 across 12 samples |
| RDS CPU utilization | 3.08% | 2.96–3.71% |
| RDS freeable memory | 5.02 GB | 5.02 GB |
| RDS connections (five-minute average) | 0.65 | 0.40–0.80 |
| RDS read IOPS | 0.26 | 0.26 |
| RDS write IOPS | 2.39 | 2.33–2.43 |
| RDS free storage | 206.57 GB | 206.57 GB |
| ALB requests | 15 total | 0–4 per five-minute period |
| ALB target response time p95 | 23 ms mean of seven sampled periods | 2–73 ms |

No target 5xx datapoints were reported in this window. Ten sequential synthetic `GET /api/health` requests returned HTTP 200; client-observed elapsed times were 93–174 ms. The S3 `infrastructure/worker-heartbeat.json` object was about 9 seconds old when checked. `TelemetrySchedulerFailures` reported zero in all twelve periods. No `TelemetryIngestionCompleted` datapoints were present; the synthetic certification connection remains disabled. A connector fetch rate, ingestion throughput, V2 analysis throughput, and saturation point were therefore not measured. EC2 memory metrics were unavailable in CloudWatch. Do not interpret missing datapoints as successful work.

## Restore drill

Point-in-time restore target: `neraium-sre-restore-20261003-0532`; source: `neraium-prod-postgres` at **2026-10-03 05:26:06 UTC**. The target uses the production VPC's private subnet group and a separate security group `sg-045aeac86ee8fcab5`, with PostgreSQL ingress only from ECS task security group `sg-01ef49d17269dd2d3`. It is not publicly accessible. RDS emitted a successful restoration event.

A one-off ECS inspection task `6dd8cc69ef9b4525aedfba12dc3924e7` used the certified API image and an existing runtime credential injected by ECS. It overrode only the database host to the restored endpoint and set `default_transaction_read_only=on`. Its exit code was 0. The task queried only `telemetry.schema_migrations`, `to_regclass` for three tables, and the transaction read-only setting. It found migration IDs **002–010** in order, and the following three tables: `telemetry.ingestion_runs`, `telemetry.relationship_lineage_artifacts_v2`, and `telemetry.endpoint_analysis_executions_v2`. The connection reported `transaction_read_only=on`. No customer rows were queried. This establishes that the point-in-time backup can be restored and read with the expected Production V2 schema and ledger.

After the successful inspection, RDS accepted deletion of the temporary instance with no final snapshot. The `db-instance-deleted` waiter completed, and the temporary security group was deleted. Final read-only lookups returned `DBInstanceNotFound` for the restore target and `InvalidGroup.NotFound` for its security group. The certified API and worker remained at 1/1 on revisions `:338` and `:332`; `/api/health` and `/api/ready` passed, and live RDS remained `available`. The isolated restore drill is complete.
