# Production Self-Monitoring

Neraium production monitors the platform itself independently from customer infrastructure analysis. The design follows the same operating sequence used by SII:

```text
Detect -> validate persistence -> classify -> explain evidence -> notify once -> recover once
```

## Monitoring architecture

```text
                                  +-------------------------+
Browser administrator ---------->| Infrastructure dashboard|
                                  +------------+------------+
                                               |
                                               v
+------------------+     every 60s     +-------------------------------+
| ECS API task     |------------------>| Production health evaluator   |
|                  |                   | - dependency probes            |
| request latency  |                   | - persistence state machine    |
| auth/RDS probe   |                   | - incident/recovery history    |
| secret metadata  |                   +---------------+---------------+
| runtime DB/disk  |                                   |
| S3 queue         |                                   v
| ECS/ALB describe |                   +-------------------------------+
+--------+---------+                   | Notification fan-out          |
         |                             | Console / SNS / email          |
         | shared S3 heartbeat         | Slack / Teams / webhook        |
         v                             +-------------------------------+
+------------------+
| ECS worker task  |
| queue heartbeat  |
+------------------+

Independent failure plane (works when the API task is unavailable):

ALB + ECS Container Insights + CloudWatch log metrics
                         |
                         v
              persistent CloudWatch alarms
                         |
                         v
                 SNS topic + OK recovery
```

The in-application state is stored as `infrastructure/production-health-state.json` in the existing encrypted shared upload-state S3 bucket, with local runtime storage used only outside split-role production. This preserves incident and recovery history across ECS task replacement. Per-incident transition markers in the same bucket prevent duplicate open or recovery notifications during overlapping rollouts. The state stores only sanitized evidence, incident transitions, and delivery results; it never stores a database URL, password, secret value, or API token.

The worker publishes `infrastructure/worker-heartbeat.json` into the existing shared upload-state bucket at most once every 30 seconds. The record contains timestamp, process role, build SHA, status, and whether a job was processed; it contains no customer data or credentials.

## Health model

`GET /api/infrastructure/health` requires administrator access in production and returns:

```json
{
  "overall_status": "healthy",
  "category": "Infrastructure Healthy",
  "subsystems": {
    "api": {},
    "auth": {},
    "runtime_db": {},
    "workers": {},
    "uploads": {},
    "notifications": {},
    "storage": {},
    "secrets": {}
  },
  "evidence": [],
  "degraded_since": null,
  "confidence": "high",
  "current_alerts": [],
  "pending_validation": [],
  "incidents": []
}
```

Checks cover:

- API startup, recent server errors, and p95 request latency
- Authentication database connectivity and latency
- Runtime database connectivity and latency
- Secrets Manager metadata access and secret age
- Last successful credential acquisition/refresh and consecutive refresh failures
- ECS API and worker desired/running task counts and recent task start events
- ALB target health
- Shared worker heartbeat age and status
- Upload queue depth, oldest pending age, and oldest processing age
- Runtime directory write/fsync, permissions, free bytes, and free percentage
- Critical startup dependency failures
- Configured notification adapters and last delivery results

## Persistence and noise controls

The current snapshot can show a failing raw signal immediately, but a notification is not created until the signal meets both its consecutive-attempt and duration threshold.

| Signal | Attempts | Minimum duration |
|---|---:|---:|
| API unavailable / no ALB targets | 5 | 4 minutes between first and fifth observation |
| Authentication database unavailable | 3 | 2 minutes |
| Runtime database unavailable | 3 | 2 minutes |
| Secrets Manager unavailable | 3 | 2 minutes |
| Credential refresh failing | 3 | 2 minutes |
| ECS API or worker tasks unavailable | 3 | 2 minutes |
| Worker heartbeat missing/stale | 3 | 2 minutes |
| Queue stalled | 3 | 5 minutes |
| Runtime storage unavailable | 3 | 2 minutes |
| Authentication, database, or API latency | 5 | 4 minutes |

CloudWatch uses the equivalent production posture:

- ECS running task loss: 3 of 3 one-minute periods
- No healthy ALB targets: 5 of 5 one-minute periods
- ALB p95 target response time above 2 seconds: 5 of 5 periods
- Target 5xx count at least 5: 3 of 5 periods
- Auth database, secret access, credential refresh, or worker iteration failure: 3 of 5 periods

One active incident is maintained per signal. Repeated unhealthy evaluations update evidence but do not send another notification. A single recovery transition resolves the incident and sends one `Infrastructure Healthy` notification. Further healthy evaluations are silent.

## Categories

- `Infrastructure Healthy`: recovery or quiet steady state
- `Infrastructure Review`: persistent latency or lower-confidence configuration gap
- `Infrastructure Degraded`: meaningful reduced service such as a queue stall
- `Infrastructure Critical`: API, authentication, secret, database, task, target, worker, or storage loss

## Notification adapters

The application always writes a structured console/log notification. Optional adapters are enabled only when their environment configuration exists:

- SNS: `NERAIUM_INFRA_ALERT_SNS_TOPIC_ARN`
- Slack: `NERAIUM_INFRA_ALERT_SLACK_WEBHOOK_URL`
- Teams: `NERAIUM_INFRA_ALERT_TEAMS_WEBHOOK_URL`
- Generic webhook: `NERAIUM_INFRA_ALERT_WEBHOOK_URL`
- Email: existing `NERAIUM_SMTP_*` and `NERAIUM_NOTIFICATION_EMAIL_RECIPIENTS`

Slack, Teams, and webhook URLs should be supplied through ECS secret references, not plaintext task-definition environment values. The deployment workflow preserves preconfigured optional secret entries.

The AWS alarm plane publishes to `neraium-prod-infrastructure-alerts`. Email subscribers come from `NERAIUM_INFRA_ALERT_EMAILS`, falling back to the bootstrap administrator email, and must confirm the normal SNS subscription email once.

Example degradation:

```text
Infrastructure Critical

What changed: Authentication database connectivity probe failed (OperationalError).
When it started: 2026-07-25T12:00:00+00:00
Subsystem: auth
Current impact: Users may be unable to sign in or validate sessions.

Evidence:
- Authentication database probe failed (OperationalError).
- Credential refresh has failed 3 consecutive attempts.
- Secrets Manager access probe failed (AccessDeniedException).

Recommended first check: Verify RDS credentials and Secrets Manager rotation, then inspect authentication logs.
Incident: auth_connectivity:1784980800
```

Example recovery:

```text
Infrastructure Healthy

What changed: Auth recovered after persistent degradation.
When it started: 2026-07-25T12:00:00+00:00
Subsystem: auth
Current impact: The previously reported infrastructure impact has recovered.

Evidence:
- Authentication database connectivity probe completed in 42 ms.
```

## Dashboard

Administrators open **Administration** and see **Production Infrastructure** before governance and user management. The dashboard refreshes every 30 seconds and includes:

- Overall health and confidence
- All subsystem cards and first evidence
- Signals still being validated, explicitly marked as not alerted
- Current incidents and recommended first checks
- Incident and recovery history
- Authentication/runtime database connectivity
- Authentication and API latency
- Worker heartbeat and age
- Last successful credential refresh
- Secret age

A healthy dashboard intentionally renders one quiet sentence plus healthy cards. Current alerts are omitted entirely when no incident is active.

## Provisioning and validation

`scripts/bootstrap-production-aws.sh` calls `scripts/configure-production-monitoring.sh`. Both are idempotent. The deploy workflow validates that:

- At least nine production alarms publish both ALARM and OK transitions to the SNS topic
- Container Insights is enabled
- API and worker log metric filters exist
- The API task has monitoring enabled and receives the correct SNS topic and ALB target group
- The task role can publish to the topic and describe the RDS secret, ECS services, and ALB target health

Manual inspection:

```bash
aws cloudwatch describe-alarms \
  --alarm-name-prefix neraium-prod- \
  --region us-east-2

aws sns list-subscriptions-by-topic \
  --topic-arn <neraium-prod-infrastructure-alerts-arn> \
  --region us-east-2

aws logs describe-metric-filters \
  --log-group-name /ecs/neraium-prod-api \
  --region us-east-2
```

Do not force an outage in production to test notifications. Failure and recovery persistence is simulated in `tests/test_production_health.py`; production validation is read-only through health, AWS alarm state, target health, and ECS task inspection.
