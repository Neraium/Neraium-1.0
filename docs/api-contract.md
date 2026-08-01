# API contract policy

## Telemetry workflow routing

`POST /api/data/upload` accepts a multipart `workflow` field. Canonical values
are `create_baseline`, `analyze_new_data`, and `extend_baseline`.

Baseline construction returns a dedicated `baseline-suitability.v1` result and
a versioned `behavioral-digital-model.v1` candidate through
`GET /api/data/baselines/jobs/{job_id}`. It never returns the canonical SII
analysis contract. See [Behavioral baseline workflows](BEHAVIORAL_BASELINE_WORKFLOWS.md).

All 141 documented HTTP operations are inventoried by `tests/test_api_contracts.py`. Request models reject undeclared top-level fields and trim declared strings. Dynamic connector configuration remains an explicitly open nested object because each connector owns its configuration schema; its serialized size and key count are bounded.

Non-upload request bodies are capped at 1 MiB. Historical telemetry uploads use the configured `max_upload_size_bytes` limit, and connector CSV uploads use the 16 MiB connector limit. Relevant identity headers, filenames, paths, strings, URLs, enums, timestamps, pagination, and numeric controls have explicit bounds. Unknown query parameters are rejected. Replay times require timezone-aware ISO 8601 values.

Errors share `detail`, `message`, and `error_type`; validation errors also include sanitized locations and types without echoing submitted values. Upload endpoints retain their richer historical state envelope (`job_id`, processing state, progress, and error fields) for frontend compatibility, but now include the common fields when raised through shared handlers. Internal exception messages are logged and replaced with a generic client message.

The shorthand `/latest-upload` and `/systems` routes are deprecated in OpenAPI and remain compatibility aliases. Admin surfaces are the connector configuration routes, auth user/session management, audit, observability, startup status, route debug, data-connection administration, and global resets; production runtime authorization tests cover unauthenticated and insufficient-role access.

## Golden Nugget historical assessment

`/api/pilot-assessments` owns the blinded two-period pilot contract. Intake is
multipart and uses the configured historical-upload size limit. Mapping,
analysis, known-event reveal, and append-only feedback are separate mutations;
the event mutation returns `409` until analysis finishes. Exact relationship
records are exported as CSV, and the full pilot assessment is exported as HTML.
See [Golden Nugget historical assessment](GOLDEN_NUGGET_HISTORICAL_ASSESSMENT.md).

## Live telemetry analysis

`/api/live-analysis` owns per-system live-analysis configuration, manual run
triggers, durable run history, live findings, and analysis health. Configuration
writes require admin access, manual runs require operator access, and reads use
the existing protected-read policy. Live analysis consumes only normalized
Phase 1 telemetry and approved behavioral models. See
[Live telemetry analysis: Phase 2](LIVE_TELEMETRY_PHASE_2.md).
