# Behavioral baseline workflows

Neraium treats baseline construction, SII analysis, and controlled learning as
three different workflows. They share telemetry parsing and mathematical
utilities, but they do not share orchestration, terminal outputs, or persisted
model state.

## 1. Create Baseline

Upload with multipart field `workflow=create_baseline`.

The dedicated `build_behavioral_baseline(...)` orchestrator:

1. validates and normalizes telemetry;
2. assesses timestamp quality, data quality, and sensor health;
3. identifies operating modes;
4. learns signal distributions and mode-conditioned relationships;
5. builds an initial relationship graph;
6. estimates empirical thresholds, lag behavior, volatility, and persistence;
7. fits expected-behavior models and validates them with a chronological
   holdout;
8. creates a versioned Behavioral Digital Model candidate; and
9. returns a `baseline-suitability.v1` report.

It does not call `run_structural_analysis_pipeline`, `run_sii_runner`, replay
generation, evidence persistence, domain interpretation, driver attribution,
or notification dispatch.

Baseline results therefore do not contain findings, anomaly observations,
physics violations, propagation paths, evidence-fusion observations,
maintenance conclusions, root-cause conclusions, or the canonical analysis
result. A recursive contract guard rejects a baseline result if one of those
artifacts is introduced.

Candidate activation is controlled by
`NERAIUM_BASELINE_APPROVAL_REQUIRED` (default `true`). When approval is
required, a suitable candidate remains `awaiting_approval` until an operator
calls the approval endpoint. An unsuitable candidate cannot be activated.

## 2. Analyze New Data Against Active Baseline

Upload with multipart field `workflow=analyze_new_data`.

This workflow requires an active Behavioral Digital Model. It records the
model ID and version in `active_baseline_reference`, then follows the SII
analysis path. Findings, observations, evidence, replay, and operational
interpretation belong only to this workflow.

The older upload behavior remains available internally as `legacy_analysis`
for compatibility with integrations that have not started sending a workflow
field. New UI actions always send one of the three canonical workflow values.

## 3. Extend Baseline Through Controlled Learning

Upload with multipart field `workflow=extend_baseline`.

This workflow also uses `build_behavioral_baseline(...)`, never the SII
detection path. It requires an active model and creates a new candidate with
`parent_model_id` and `parent_version` lineage. It never mutates the active
model in place. Approval policy applies to the new version exactly as it does
to an initial candidate.

## Persistence separation

Analysis artifacts continue to use the latest-upload/result/evidence stores.
Behavioral models use a workspace-scoped store with separate records for:

- the model index;
- each immutable version candidate;
- the latest candidate pointer;
- the active model pointer; and
- each baseline-suitability result.

Baseline job progress uses the common upload-status transport so the browser
can poll one job protocol, but baseline jobs do not publish themselves as the
latest SII analysis and do not write evidence records.

## Asynchronous upload lifecycle

Baseline upload transport and baseline processing are separate lifecycle phases.
The production path is:

1. The API stores the uploaded object and creates a dataset identity.
2. Completion of the transfer creates a separate processing job identity and
   persists the `dataset_id` to `job_id` mapping before enqueueing work.
3. The worker restores the stored dataset, parses the CSV, validates signals,
   learns relationships, constructs the candidate baseline, and commits the
   result record.
4. The worker verifies that `GET /api/data/baselines/jobs/{job_id}` can read the
   committed result. Only then does it publish terminal `COMPLETE` status.
5. The browser polls `/api/data/upload-status/{job_id}` using only `job_id`. An
   HTTP 200 response is transport success; the `status`/`job_state`, result
   availability flags, and structured failure fields determine workflow state.
6. A short bounded consistency retry is allowed when a result object is not yet
   visible. Polling otherwise continues until completion, explicit failure, or
   the documented 30-minute server-analysis deadline.

The identifiers have distinct meanings and must not be substituted:

- `dataset_id`: the stored telemetry object/dataset record;
- `job_id`: the asynchronous import/baseline processing attempt;
- `upload_session_id`: the multipart or presigned transfer session; and
- `request_id`: the request correlation identity recorded by API and worker
  logs.

A failed processing attempt retains the stored dataset. `Retry Processing`
re-enqueues the existing job against that dataset and never falls back to a new
upload. `Choose Another File` abandons the browser workflow and clears dataset,
job, poll, completion, and error state.

Worker failures publish both the existing compatibility fields and this
structured contract:

```json
{
  "status": "FAILED",
  "job_state": "failed",
  "stage": "import | validation | relationship_learning | baseline_creation",
  "errorCode": "machine_readable_code",
  "userMessage": "Safe operator-facing reason",
  "technicalMessage": "OriginalExceptionType: original exception message",
  "retryable": true,
  "datasetId": "stored-dataset-id",
  "jobId": "processing-job-id",
  "requestId": "correlation-request-id"
}
```

The technical message is intended for the collapsed diagnostic UI and logs.
Worker exception logs include the dataset, job, request, canonical stage,
exception type, and stack trace.

## API

`POST /api/data/upload`

Multipart fields:

- `file`: CSV, TXT, or JSON telemetry.
- `workflow`: `create_baseline`, `analyze_new_data`, or `extend_baseline`.
- `approval_required`: optional boolean override for baseline workflows.

Baseline endpoints:

- `GET /api/data/baselines`
- `GET /api/data/baselines/jobs/{job_id}`
- `GET /api/data/baselines/{baseline_id}`
- `GET /api/data/baselines/candidates/{model_id}`
- `POST /api/data/baselines/candidates/{model_id}/approve`

Every baseline status and result publishes `sii_engine_invoked: false`.
Automated tests monkeypatch the SII runner to fail if either baseline workflow
reaches it.


## Exact selection and activation consistency

A completed baseline result carries `job_id`, `upload_id`, `dataset_id`,
`baseline_candidate_id`, `established_baseline_id`, `portfolio_id`, and
`system_id`. The completion response is the selection authority. Clients
persist these identifiers and hydrate the completion view only through
`GET /api/data/baselines/{baseline_id}` in the matching workspace; the
portfolio-level state endpoint is not a substitute for an exact selection.

Activation uses an activation-critical persistence barrier. The new model and
active pointer are durably written before a terminal automatic-activation
result is published, and the previous model is superseded only after the new
pointer exists. A shared-state write failure fails the workflow rather than
reporting completion with the previous model still active.
