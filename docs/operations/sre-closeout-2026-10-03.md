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

## Final SRE closeout — 2026-10-03 07:11 UTC

The checks below use AWS operational metadata, the approved synthetic V2 execution from the release certification, and infrastructure probes. No customer telemetry or credential value was printed or committed.

### Alert delivery

- The existing SNS topic is `arn:aws:sns:us-east-2:680779862188:neraium-prod-infrastructure-alerts`. AWS `list-subscriptions-by-topic` returned one confirmed email subscription for `craig@neraium.com`: `arn:aws:sns:us-east-2:680779862188:neraium-prod-infrastructure-alerts:aae5659b-3a48-4a2f-a316-f88e3bcdc318`. Topic attributes reported one confirmed and zero pending subscriptions.
- A controlled `sns:Publish` to that existing topic returned message ID `ae28c9db-0463-57b8-81bb-aae1a3d5d7f2` with subject **Neraium production SRE controlled alert test 2026-10-03**. AWS/SNS `NumberOfNotificationsDelivered` reported one in the 06:45 UTC five-minute period and `NumberOfNotificationsFailed` reported zero. The operator explicitly confirmed receiving that subject at `craig@neraium.com`, visible receipt time **11:49 PM local time**. The local timezone was not supplied, so no UTC receipt time is inferred.
- All 17 `neraium-prod-` CloudWatch alarms were `OK`, had actions enabled, and routed both ALARM and OK actions to that topic. The SNS path and human receipt passed. An actual CloudWatch ALARM state transition was not induced; alarm dispatch is supported by AWS configuration evidence rather than a forced incident.

### V2-safe image and rollout

- The generic backend workflow's unsafe V1 identity and disabled-egress defaults were removed. It now requires V2 identity, controlled egress, disabled dynamic secret writes, and required secret references; it selects the serving service task definitions and checks protected environment variables, all secret bindings, roles, and network settings before registering a candidate. Automatic `main` deployment was disabled, and the legacy connector overlay is blocked before AWS writes because its base image is older than the certified V2 image. Future generic backend releases require separate image-lineage recertification.
- The dedicated SRE overlay uses the certified image `sha256:d57f44d3f1af85d6a6eddfcf29c8b99198a63cd5de58ae21408d7fae90594816` as its base and copies only the four application files changed in SRE implementation commit `74a542562f4569f9e72c58a0efcd96ff0801b2af`. Each file in the certified image matched its pre-SRE source at `627dc886` before the overlay. The image was built from a clean detached checkout of `74a54256`, parsed its four Python modules, and was pushed at **06:55:55 UTC** as `neraium-prod-api:sre-v2-74a542562f4569f9e72c58a0efcd96ff0801b2af`, digest `sha256:635d76fd2ff022bc2b9036ca4f1ca5153651a0b6b749cc8ff19cba347a06fa0b`.
- A read-only preflight established that both serving services were on certified revisions and digest at 1/1, that health/readiness and dependencies passed, and that the operator SNS subscription was confirmed. The deployment script constructed image-only task-definition changes and pinned the new image by digest. It registered worker `neraium-prod-worker:333` at **06:56:02.471 UTC** and API `neraium-prod-api:339` at **06:56:02.543 UTC**, updated both services, and waited for stability. Its rollback target remained the certified `:332`/`:338` pair; rollback was not needed.
- Post-rollout ECS reported each service `ACTIVE`, desired/running/pending **1/1/0**, with one `COMPLETED` primary deployment. Running task image digests were both `sha256:635d76fd2ff022bc2b9036ca4f1ca5153651a0b6b749cc8ff19cba347a06fa0b`. Compared with certified `:332`/`:338`, both new task definitions have **identical complete environment arrays and ECS secret-binding arrays**, as well as identical task role, execution role, and network mode. This proves preservation of `physical-endpoint-keyed.v2`, controlled egress `true`, dynamic secret writes `false`, both telemetry/runtime database bindings, executor URL, CA trust and authentication secret reference. The Network Firewall `neraium-prod-v2-connector-egress` was `READY` and `IN_SYNC`, with its policy `ACTIVE`.

### Post-deployment operational and product checks

- Public `GET /api/health` and `GET /api/ready` each returned HTTP 200 after rollout. Live `neraium-prod-postgres` was `available`, encrypted, deletion protected, with seven-day backup retention. Connector executor EC2 `i-081d0aba82dba64e7` was running with system and instance checks `ok`. A one-off ECS task on the production API network made a CA-verified HTTPS `GET /health` to the configured private executor URL, checked the healthy response, and exited 0: `9c303f669c804432adec4fced0ca986e`. SSM reported `ConnectionLost`, but direct TLS health from the production network passed.
- A read-only one-off ECS probe of the previously certified synthetic execution exited 0: `12549df1db864a5f97c781e7d93124f2`. It exercised the deployed V2 list and detail projection, verified the stored result digest and lineage, and checked that a foreign workspace scope cannot retrieve the execution. No result payload was printed. An initial probe `2743edec3fb4470b8fe1128ef6f6c996` exited 1 because the probe imported the scope helper from the wrong module; it did not reach the database. The corrected probe passed. Public unauthenticated V2 detail returned HTTP 401.
- The new API task emitted `production_health_evaluated` in CloudWatch (16 events counted on its new log stream at the final check), and the worker emitted `worker_loop_started`. A second successful synthetic read probe `156dd0c30b2942648db75eb39181009c` invoked the deployed retrieval-completed event hook; it exited 0, the `telemetry_v2_retrieval_completed` log event was observed at **07:07 UTC**, and the `Neraium/Production` `TelemetryV2RetrievalCompleted` metric filter reported **1** in the 07:07 UTC period. This is a controlled instrumentation probe, not an authenticated customer API request. All five API and eleven worker metric filters remained present; all 17 alarms remained OK with actions enabled and SNS routing. Conditional failure/ingestion events were not forced on production.
- The final focused SRE, monitoring, scheduler, V2 projection, persistence, authorization, scope, configuration, and deployment-contract suite completed **96 passed, 1 skipped** in 43.78 seconds. The skip requires `NERAIUM_TEST_TELEMETRY_RUNTIME_DSN`, which is not configured locally. Workflow YAML parsed. `git diff --check` and `git diff --cached --check` passed. Existing release certification remains the evidence for the full authenticated API flow and restart retrieval; this closeout added a deployed-image read-only synthetic projection and live unauthenticated denial check.
- The point-in-time restore drill above remains PASS. At **07:11 UTC**, read-only lookups again returned `DBInstanceNotFound` for `neraium-sre-restore-20261003-0532` and `InvalidGroup.NotFound` for `sg-045aeac86ee8fcab5`. The initial idle baseline above remains PASS as a resource observation only. It does **not** establish ingestion throughput, API concurrency, saturation, or a maximum production rate.

### AWS changes and limits

Created: one ECR image tag/digest and ECS task-definition revisions `:339`/`:333`. Modified: the existing API and worker ECS services to serve those revisions; one controlled SNS publication through the existing topic. Three verification ECS tasks were started and reached `STOPPED` (`9c303f669c804432adec4fced0ca986e`, `12549df1db864a5f97c781e7d93124f2`, `156dd0c30b2942648db75eb39181009c`); the failed initial probe `2743edec3fb4470b8fe1128ef6f6c996` also stopped. No live database, security group, firewall, or alarm was changed in this final phase. No production resource was deleted. The earlier isolated restore target and temporary security group were deleted only after drill completion. The temporary ECR Docker login was removed with `docker logout` after the push.

Operational limitations: no production alarm state was deliberately forced; conditional failure events were not generated; the deactivated certification account was not reactivated for a new authenticated API read; capacity remains an idle baseline with no saturation test. These limits do not change the successful controlled alert receipt, direct executor TLS check, deployed V2 synthetic persistence/retrieval and scope probe, or certified V2 release evidence.
