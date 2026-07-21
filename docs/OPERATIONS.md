# Production Operations Guide

This guide defines the production operating contract for the Neraium backend. It covers process roles, configuration, health probes, logs, shutdown behavior, monitoring, and first-response diagnostics. Product behavior and API payload contracts are documented separately.

## Process model and startup order

Production uses two process roles from the same image:

- `api`: serves HTTP and writes accepted uploads to shared state.
- `worker`: claims and processes queued uploads. It does not run Uvicorn.
- `all` or `monolith`: local/single-process mode; the API also starts its upload worker.

Startup validates configuration before binding the HTTP port or entering the worker loop. Required runtime database initialization, default connection initialization, and explicitly enabled worker/poller startup are fail-fast. A failed API deployment should never become ready. Startup proceeds in this order:

1. Parse and validate environment.
2. Configure JSON logging.
3. Configure and initialize the runtime directory/database.
4. Recover stale queue claims and prune retention-bound records.
5. Connect and migrate the authentication store (PostgreSQL in production API roles).
6. Warm the latest-upload cache.
7. Initialize the default data connection.
8. Start enabled background services.
9. Mark startup complete and begin serving.

For split-role production, both tasks must use the same `NERAIUM_UPLOAD_STATE_BUCKET`. Local runtime files are not shared across ECS tasks.

## Health and readiness

Use separate load-balancer and deployment probes:

| Probe | Purpose | Success |
|---|---|---|
| `GET /api/health` (or `/health`) | Process liveness and recorded fatal/degraded state | HTTP 200 and `status=ok` |
| `GET /api/ready` | Lightweight traffic readiness | HTTP 200 and every existing `checks` value is `ok` |
| `GET /api/ready?verbose=true` | Operator diagnostic; includes queue, upload session, and runner details | Same readiness status, with diagnostic detail |

Readiness actively checks the runtime database and reports startup, authentication-store initialization, default-connection, and split-role shared-state state. It does not make an S3 network request on every probe; `shared_upload_state=ok` confirms configuration, not current AWS reachability. Use upload queue/error metrics and CloudWatch AWS API errors to monitor that dependency.

Do not point a high-frequency load-balancer probe at `verbose=true`. It performs additional persisted-state reads.

## Logging contract

Production defaults to newline-delimited JSON on stdout (`LOG_FORMAT=json`). Every managed log contains `timestamp`, `level`, `logger`, `event`, and `message`. Request logs also carry `request_id` and `correlation_id`; upload flows carry `upload_session_id` when available. Exceptions include a sanitized type, message, and stack trace.

`X-Request-Id` and `X-Upload-Session-Id` accept only 1-128 characters from letters, digits, `.`, `_`, `:`, and `-`. Invalid values are rejected before request handling so clients cannot inject log lines. The API returns the accepted/generated request ID in `X-Request-Id`.

The formatter redacts authorization values, cookies, passwords, tokens, API keys, access codes, embedded URL credentials, and AWS access-key IDs. Avoid logging telemetry payloads, request headers, notification URLs, database DSNs, or secret environment values. Redaction is defense in depth, not permission to log secrets.

Identical non-error messages are suppressed for 30 seconds by each managed process. Idle queue polls and health traffic log at `DEBUG`; completed work, lifecycle transitions, and diagnostic failures remain visible at `INFO` or above.

Useful lifecycle events include:

- `runtime_services_starting`, `runtime_services_started`, `runtime_services_stopped`
- `http_request_completed`
- `upload_lifecycle_event`, `upload_queue_lifecycle_event`, `upload_session_event`
- `upload_worker_started`, `upload_worker_stopped`
- `data_connection_poller_started`, `data_connection_poller_stopped`
- `evidence_run_persisted`
- `sii_state_published`
- `readiness_dependency_failed`

## Configuration reference

All values are read at process startup. Invalid enums, booleans, ports, positive limits, regexes, notification URLs, and incomplete SMTP settings fail startup with the variable name in the error. Never place real secrets in environment files committed to source control.

### Required production settings

| Variable | Valid/example value | Operational purpose |
|---|---|---|
| `APP_ENV` | `production` or `prod` | Enables production validation and controls |
| `BACKEND_HOST` | `0.0.0.0` | Bind address |
| `BACKEND_PORT` | `8080` | Bind port, 1-65535 |
| `CORS_ORIGINS` | comma-separated explicit origins | Browser allowlist; `*` is rejected in production |
| `CORS_ORIGIN_REGEX` | valid Python regex | Optional domain allowlist; defaults to Neraium domains |
| `NERAIUM_RUNTIME_DIR` | `/mnt/neraium-runtime` | Explicit writable runtime path; required in production |
| `NERAIUM_BUILD_SHA` | deployed commit SHA | Its 12-character prefix is included in diagnostics; the ECS workflow pins the full value |
| `NERAIUM_PROCESS_ROLE` | `api` or `worker` | Selects process behavior |
| `NERAIUM_UPLOAD_STATE_BUCKET` | shared S3 bucket | Required operationally for split API/worker state |
| `NERAIUM_AUTH_DATABASE_URL` | PostgreSQL DSN from Secrets Manager | Required for production API/monolith authentication persistence |
| `NERAIUM_API_TOKEN` | secret-manager injection | Service authentication secret where configured |

Bootstrap passwords, API tokens, SMTP passwords, webhook URLs, and authenticated database URLs must be injected through the deployment platform's secret facility. In ECS, use task-definition `secrets` backed by AWS Secrets Manager or SSM Parameter Store; do not put them in the plain `environment` array or workflow logs.

### Runtime and logging controls

| Variable | Default | Notes |
|---|---:|---|
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `LOG_FORMAT` | `json` | `json` for production, `console` for local use |
| `NERAIUM_START_BACKGROUND_WORKERS` | role-dependent | Defaults true for `all`, `monolith`, and `worker` |
| `NERAIUM_START_DATA_POLLER` | `false` | Start scheduled telemetry polling |
| `NERAIUM_SHUTDOWN_TIMEOUT_SECONDS` | `30` | Per-service graceful join budget |
| `NERAIUM_MAX_UPLOAD_SIZE_BYTES` | 10 GiB | Set a production limit aligned with ALB/CDN controls |
| `NERAIUM_MAX_PENDING_UPLOAD_JOBS` | `50` | Queue admission bound |
| `NERAIUM_CSV_CHUNK_SIZE_ROWS` | `5000` | Streaming parser chunk |
| `NERAIUM_CSV_PROGRESS_UPDATE_EVERY` | `5000` | Progress publication interval |
| `NERAIUM_MAX_INGESTION_ANALYSIS_ROWS` | `100000` | Ingestion analysis bound |
| `NERAIUM_UPLOAD_QUEUE_RETENTION_DAYS` | `14` | Runtime queue/history pruning |
| `NERAIUM_EVIDENCE_RUN_RETENTION_DAYS` | `45` | Evidence retention |
| `NERAIUM_SII_MAX_VECTOR_ROWS` | `4096` | Vector analysis bound |
| `NERAIUM_SII_RECENT_VECTOR_TAIL` | `512` | Recent vector tail, minimum 100 |
| `NERAIUM_INLINE_REPLAY_GENERATION` | test-dependent | Explicit true/false for deployment clarity |
| `NERAIUM_UPLOAD_STATE_PREFIX` | `upload-state/` | S3 key namespace |
| `NERAIUM_DEFAULT_TELEMETRY_URL` | empty | Optional default REST telemetry source |

### Notification settings

`NERAIUM_NOTIFICATION_WEBHOOK_URL` must be an absolute HTTP(S) URL without embedded credentials. SMTP delivery is enabled only as a complete set: `NERAIUM_SMTP_HOST`, `NERAIUM_NOTIFICATION_EMAIL_RECIPIENTS`, and `NERAIUM_SMTP_SENDER`. If `NERAIUM_SMTP_USERNAME` is set, `NERAIUM_SMTP_PASSWORD` is required, and vice versa. `NERAIUM_SMTP_PORT` defaults to 587 and `NERAIUM_SMTP_USE_TLS` defaults true.

## Graceful shutdown and resource ownership

The API stops the scheduled poller, stops the background queue worker, waits for request-dispatched upload workers, clears in-process rate-limit state, and logs shutdown duration/failures. Worker-only processes handle `SIGTERM` and `SIGINT`, finish the current queue iteration, and exit before claiming another job.

Set the orchestrator stop grace period above the application's shutdown budget plus expected queue operation latency. A conservative starting value is 120 seconds for `NERAIUM_SHUTDOWN_TIMEOUT_SECONDS=30` because poller, worker, and request-worker waits are sequential. Long CPU-bound analysis is not forcibly terminated by the application; the queue's stale-claim recovery protects the next process if the orchestrator kills it.

Temporary upload files and restored shared upload sources are deleted in `finally` paths after processing. Monitor runtime volume capacity and inode use. In-memory rate-limit buckets are swept after expiry, and upload-status caches retain at most 1,000 jobs per process; persisted history remains authoritative.

## Monitoring recommendations

At minimum alert on:

- `/api/ready` non-200 for 2 consecutive minutes
- container restarts or startup failure events
- `neraium_queue_pending` continuously above zero, and queue age from verbose readiness
- `neraium_evidence_runs_failed > 0`
- `neraium_sparse_upload_rate > 0.20`
- `neraium_unknown_profile_rate > 0.15`
- `neraium_flagged_room_rate > 0.35`
- `readiness_dependency_failed`, `*_startup_failure`, `*_shutdown_timeout`
- S3 `AccessDenied`, throttling, or write failures in API/worker logs
- runtime filesystem usage above 70% and memory/RSS growth
- absence of `sii_state_published` after completed upload work

Scrape `/api/observability/metrics` with an admin credential over TLS. The current metrics are process-generated snapshots and are not a durable metrics store; use Prometheus/CloudWatch collection and retention outside the application.

Recommended dashboard dimensions are process role, build SHA, task/container ID, event, HTTP status, request ID, upload session ID, and job ID. Never make secrets or raw telemetry dashboard dimensions.

## Deployment safety

Before deployment:

1. Validate task definitions contain both API and worker roles and the same upload-state bucket.
2. Confirm secrets are in task-definition `secrets`, not plain environment values.
3. Confirm the runtime mount is writable and sized for the largest accepted upload plus working copies.
4. Set the load balancer health path to `/api/health`.
5. Set deployment verification to `/api/ready`.
6. Keep the previous task definition revision available for rollback.
7. Run the backend test suite, frontend build/tests, dependency audits, and production smoke.

After deployment, verify build SHA, role, shared-state backend, readiness checks, a small upload through `COMPLETE`, upload and evidence persistence across a clean restart, SII state publication, and a clean worker shutdown in staging. The smoke script requires an explicit `BASE_URL` or `API_BASE_URL`; it never selects a production target by default.

## Troubleshooting

### Process exits before listening

Read the first configuration error. It names the invalid variable. Common causes are an unset production runtime directory, wildcard production CORS, invalid boolean text, an unknown process role, or partial SMTP settings.

### Health is 200 but readiness is 503

Inspect `checks`, `failed_modules`, `config_warnings`, and `diagnostics`. A runtime DB failure means the runtime volume is missing, read-only, full, or corrupt. An authentication-store startup failure means the PostgreSQL secret, network path, credentials, or migration permissions are invalid. A shared-upload-state failure in split roles means the bucket is absent from configuration.

### Upload remains pending

Compare API `job_queued` with worker `job_claimed` using `job_id` and `request_id`. Verify both roles use the same bucket/prefix and IAM task role. Inspect queue operational metrics and worker startup logs.

### Evidence or SII state is missing

Find `evidence_run_persisted` and `sii_state_published` for the job. Any persistence exception includes a sanitized stack trace. Check runtime volume and shared-state write errors.

### Shutdown exceeds the grace period

Find `upload_worker_shutdown_timeout`, `data_connection_poller_shutdown_timeout`, or `request_upload_workers_shutdown_timeout`. Increase the orchestrator grace period only after confirming the current operation is bounded and not stuck on an external dependency.
