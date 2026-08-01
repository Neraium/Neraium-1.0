# Live telemetry analysis: Phase 2

Phase 2 consumes accepted Phase 1 normalized telemetry, builds rolling comparison
windows, invokes the existing Neraium relationship intelligence against an
approved Behavioral Digital Model (BDM), and maintains live finding state. It
does not change ingestion semantics, create baselines, run historical assessment
workflows, or introduce a frontend.

## Architecture and reused intelligence

Live orchestration is implemented in
`app.services.live_analysis`. Window construction is isolated in
`app.services.live_windows`, and `app.services.live_intelligence` is a thin
adapter between approved BDM expected models and existing production services.

The adapter reuses these entry points:

- approved baseline storage: `app.services.behavioral_model_repository.read_model`
- relationship and persistence rules:
  `app.services.pilot_assessment.evaluate_relationship_against_baseline`
- relationship scoring:
  `app.services.relationship_baselines.score_relationship_importance`
- deterministic classification:
  `app.services.finding_classification.classify_finding`
- evidence generation:
  `app.services.upload_evidence.build_evidence_record_from_result`

`evaluate_relationship_against_baseline` exposes the historical assessment's
existing relationship-fit thresholds and persistence-window evaluator. The
historical path calls the same function; thresholds and output behavior were not
changed.

Approved BDMs currently persist unconditional (`all_operation`) and
mode-conditioned expected models, but do not persist the empirical mode
assignment thresholds required to assign new rows safely. Live analysis
therefore evaluates only accepted `all_operation` expected models. It does not
guess a mode or fabricate baseline rows.

## Rolling-window rules

For each configured system, the watermark is processing time minus
`allowed_lateness_minutes`, floored to the analysis interval. The comparison
window ends at that watermark and begins `comparison_window_minutes` earlier.

The builder:

- reads only `good` and mildly `out_of_order` normalized Phase 1 rows;
- includes accepted late values when their source timestamp falls in the window;
- excludes rejected/quarantined values and signals absent from the approved BDM;
- normalizes bounds and row timestamps to UTC and sorts chronologically;
- deterministically selects the newest ingested value when multiple sources
  provide the same canonical signal and timestamp;
- produces one rectangular row per observed timestamp with missing cells set to
  null;
- derives expected slots from the median observed cadence and calculates
  per-signal and overall coverage across the entire configured time window; and
- never interpolates, fills, or invents values.

At least 18 timestamp rows, two usable canonical signals, an eligible approved
expected model, and the configured coverage percentage are required.

## Readiness and run state

A run is skipped without calling analytics when the configuration is disabled,
the approved baseline is unavailable, ingestion health is blocking, telemetry is
unavailable, coverage is insufficient, signals are insufficient, the window
already exists, or another run owns the system claim. Skip reasons are durable
and update live-analysis health. Missing or delayed data never creates or
resolves a physical finding.

Runs transition through `pending`, `running`, and one terminal state:
`completed`, `skipped`, or `failed`. A unique key over system, baseline,
window start, and window end makes retries idempotent. A partial unique index
permits only one running analysis for a system. A pending or running record older
than 15 minutes or two analysis intervals, whichever is longer, is failed
auditably on recovery so a worker restart cannot leave a permanent claim.

## Finding lifecycle

The stable deduplication key is SHA-256 over:

`system_id + approved_baseline_id + expected_behavior_model_id`

A detected relationship begins in `observing` unless the existing persistence
evaluator has already met its threshold. Persistent detections open the same
record; later detections update its last-observed timestamp, score,
classification, evidence, source run, and persistence state. A relationship is
resolved only when a successful analysis evaluates that same approved expected
model as aligned with baseline. Skipped and failed runs never resolve findings.

Live findings are stored separately from historical assessment findings.
Ingestion health, live-analysis health, and physical findings remain separate
concepts.

## API and authorization

All routes use the existing protected API conventions under
`/api/live-analysis`.

- configuration create/update/enable/disable: admin
- manual run trigger: operator or admin
- configuration, run, finding, and health reads: existing protected-read policy

Important routes include:

- `POST /api/live-analysis/configurations`
- `GET /api/live-analysis/configurations`
- `PUT /api/live-analysis/configurations/{system_id}`
- `POST /api/live-analysis/configurations/{system_id}/enable`
- `POST /api/live-analysis/configurations/{system_id}/disable`
- `POST /api/live-analysis/systems/{system_id}/runs`
- `GET /api/live-analysis/runs`
- `GET /api/live-analysis/runs/{run_id}`
- `GET /api/live-analysis/findings`
- `GET /api/live-analysis/findings/{finding_id}`
- `GET /api/live-analysis/health`

Example configuration:

```bash
curl -X POST http://127.0.0.1:8010/api/live-analysis/configurations \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "system_id": "resort-chilled-water",
    "enabled": true,
    "approved_baseline_id": "bdm-v1-example",
    "analysis_interval_seconds": 300,
    "comparison_window_minutes": 60,
    "minimum_coverage_percent": 80,
    "allowed_lateness_minutes": 5
  }'
```

## Worker

The existing backend worker loop calls `run_due_live_analyses()` independently
on every poll and continues after a single-system failure. A standalone worker
is also available for external schedulers and operations:

```bash
PYTHONPATH=backend .venv/bin/python -m app.live_analysis_worker --once
```

Omit `--once` to run a graceful SIGINT/SIGTERM-aware process loop. The command
logs concise counts only; telemetry payloads and credentials are not logged.
