# Backend job progress contract

Neraium exposes long-running upload, historical-ingestion, baseline-construction,
and comparison-analysis progress as `job-progress.v1` inside the existing upload
job/status payload. The contract is backend-authoritative and is persisted with
the same tenant- and workspace-scoped upload state as the job. It does not add a
second state store.

## Shape

`job_progress` contains:

- `contract_version`, `job_id`, and `workflow`
- `status`: `queued`, `processing`, `waiting`, `retrying`, `completed`,
  `failed`, or `cancelled`
- `stage` and `substage`
- `completed_units`, `total_units`, `percent_complete`, and `unit_type`
- `message`, `started_at`, `updated_at`, `elapsed_seconds`
- `last_worker_heartbeat_at`, `seconds_since_worker_heartbeat`,
  `seconds_since_update`, and `stalled`
- `retryable`, a user-safe `error`, and bounded non-secret `metadata`
- ordered `workflow_steps` and ordered detailed `operations`
- `overall_percent_complete` and `overall_basis`

`percent_complete` is null unless the active operation has a safe total. A
completed operation is 100%. No stage-start percentage is generated.
The top-level active-operation fields are a convenience projection of the
operation named by `substage`; the named `operations` record is canonical and
status reads keep the projection synchronized with it.

`overall_percent_complete` uses the documented
`equal_completed_declared_substages` rule. Every operation that the selected
workflow actually runs is one work item. Completed operations contribute one;
an active operation contributes `completed_units / total_units` only when its
total is known. The result is floored to a whole percentage and clamped to
0–100. Baseline workflows currently declare 22 operations; comparison-analysis
workflows declare 33. Historical review rebuilds declare 14 because they stop at
`readiness_evaluation` and do not create a separate analysis snapshot. This is
deterministic stage-completion weighting, not a
time or remaining-work estimate. Equal weighting is used because these are the
only stable cross-dataset work units: rows, signals, pairs, and persistence
checks cannot be added together meaningfully. No duration weighting or ETA is
claimed.

The same rule is applied within each workflow step. A step percentage therefore
means “declared substages completed,” plus a measurable fraction of the one
active substage. Merely starting a substage contributes zero.

## Workflow stages and units

All workflows expose completed upload transfer/source-persistence operations,
then the historical trust pipeline. The stable operation IDs and their actual
units are:

| Stage | Substage | Work unit |
| --- | --- | --- |
| upload | `receiving` | transfer operation; browser XHR separately reports measured bytes while the request is in flight |
| upload | `source_persisted` | persistence operation |
| validate | `parse_source` | source rows; indeterminate until the first complete pass establishes the total |
| validate | `schema_detection` | source columns |
| validate | `timestamp_detection` | source columns evaluated |
| validate | `timestamp_quality` | source rows evaluated |
| validate | `signal_inventory` | candidate signals |
| validate | `unit_detection` | candidate signals |
| validate | `semantic_mapping` | candidate signals |
| validate | `data_quality_profiling` | candidate signals |
| validate | `unit_normalization` | source rows normalized |
| validate | `canonical_dataset_build` | hash and immutable-persistence checks |
| validate | `configuration_awareness` | signals considered for configuration context |
| validate | `readiness_evaluation` | deterministic readiness decision |
| validate | `analysis_snapshot_build` | source rows prepared for the bounded analysis snapshot |

A manual historical-review rebuild uses the same validation operations and
measured units through `readiness_evaluation`. It deliberately omits
`analysis_snapshot_build`, baseline learning, and comparison analysis because
the review endpoint does not execute those tasks. The attempt is persisted on
the dataset's existing job/status record with `workflow=historical_review`
inside `job_progress`; the enclosing original workflow remains intact when one
exists.

Baseline jobs then expose:

| Stage | Substage | Work unit |
| --- | --- | --- |
| learn | `select_usable_signals` | source columns evaluated; selected signal count is metadata |
| learn | `build_operating_context` | analysis rows |
| learn | `compute_baseline_statistics` | usable signals |
| learn | `learn_relationships` | eligible signal pairs across eligible operating-mode groups |
| learn | `fit_expected_models` | retained relationship candidates evaluated |
| learn | `persistence_checks` | candidate write and readback checks |
| ready | `finalize_baseline` | finalization operation |

Comparison jobs expose each module actually invoked by the authoritative SII
orchestrator: `prepare_inputs`, `signal_drift`, `relationship_analysis`,
`operating_modes`, `data_conditions`, `sensor_health`, `empirical_thresholds`,
`mode_conditioned_baseline`, `relationship_graph_analysis`,
`fixed_persistence`, `adaptive_persistence`, `temporal_analysis`,
`multiscale_analysis`, `covariance_analysis`, `physics_reasoning`,
`behavioral_model`, and `evidence_fusion`, followed by `finalize_analysis`.
Each engine module is a 0/1 module work unit. The engine's old fractional
callback values are deliberately ignored because they are lifecycle markers,
not measurements.

## Persistence, isolation, and resume behavior

The snapshot is embedded under `job_progress` in the existing upload job JSON.
The existing runtime database/local JSON or configured shared S3 backend stores
it. Existing dataset-scope validation protects reads, and progress metadata does
not contain a tenant selector that can override the enclosing job scope.
Per-job upload status/result keys are tenant/workspace scoped; reads include a
scope-verified fallback for records written before that key migration. Completed
operations and counters are preserved on failure. A retry starts a fresh
progress attempt and records the prior failed substage, completed operation IDs,
and retry count in attempt-lineage metadata. Counters are monotonic within an
operation and late callbacks from an earlier operation are ignored.
Once an upload/evaluation attempt publishes `COMPLETE`, later callbacks from
that attempt cannot restore `PROCESSING`; an explicit historical-review rebuild
starts a new progress attempt instead.

## Heartbeat and queue semantics

Every persisted worker progress update records `last_worker_heartbeat_at`.
Status reads calculate elapsed/staleness fields without writing. The default
stall threshold is 120 seconds (`NERAIUM_PROGRESS_STALL_SECONDS`). A stale job is
reported as lacking a recent update, not automatically failed.

Queue ownership is authoritative: a pending queue row is queued even if an API
thread has returned; only a claimed/processing queue row is reported as worker
processing. The newest claimed-queue timestamp or persisted worker progress
heartbeat is exposed separately from the last progress change. This prevents
“queued” and “analysis active” from appearing at the same time.

## Update frequency and performance

Substage transitions and terminal updates are persisted immediately. Repeated
counter updates within one substage are limited to one durable update every two
seconds by default (`NERAIUM_PROGRESS_WRITE_INTERVAL_SECONDS`). Producers report
at batch boundaries (normally 5,000 rows, 25 signals/pairs, or 10 small model
items), never per row. The frontend polls the
existing status endpoint at its bounded interval, deduplicates in-flight polls,
keeps the latest snapshot across transient failures, and stops at terminal
state. The existing SSE endpoint remains available; no new realtime transport
is introduced.

The repeatable realistic-workload benchmark and recorded results are in
[`JOB_PROGRESS_BENCHMARK.md`](JOB_PROGRESS_BENCHMARK.md).

## API and compatibility

`GET /api/data/upload-status/{job_id}` remains the status read and has the stable
OpenAPI operation ID `getUploadJobStatusV1`. GET enriches elapsed/stall values in
the response only and never persists. Existing top-level lifecycle fields remain
for older clients. When `job-progress.v1` is present, their numeric progress is
derived from `overall_percent_complete`; the frontend never turns a lifecycle
stage name into a percentage. Clients should use `job_progress` for all new UI.

Failures retain prior operation states, the failed substage, a user-safe message,
and retryability when the worker knows it. Technical diagnostics remain in the
existing privileged diagnostic fields rather than `job_progress.error`.
