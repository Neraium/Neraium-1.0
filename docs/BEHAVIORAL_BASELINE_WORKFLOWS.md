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

### Baseline progress contract

Baseline jobs publish `job_type=baseline_construction` and
`progress_state_machine=baseline_construction.v1`. Their only top-level stages
are `Import`, `Validate`, `Map`, `Learn`, `Review`, and `Ready`. `Learn` may
publish these ordered steps:

1. Validating historical coverage
2. Assessing data quality
3. Checking sensor suitability
4. Identifying operating modes
5. Learning signal behavior
6. Learning relationships
7. Building behavioral graph
8. Estimating empirical thresholds
9. Fitting expected-behavior models
10. Creating candidate baseline

Baseline status payloads do not contain the monitoring `analysis_state`,
`contract_stage`, or propagation-progress fields. The frontend selects this
state machine from the workflow/job type and rejects monitoring labels on the
baseline rendering path.

The terminal result has `result_type=baseline_suitability_report`, is titled
`Baseline Suitability Report`, and contains a
`candidate_behavioral_digital_model`. It is not an SII analysis result.

## 2. Analyze New Data Against Active Baseline

Upload with multipart field `workflow=analyze_new_data`.

This workflow requires an active Behavioral Digital Model. It records the
model ID and version in `active_baseline_reference`, then follows the SII
analysis path. Findings, observations, evidence, replay, and operational
interpretation belong only to this workflow.

Monitoring jobs publish `job_type=monitoring_analysis` and
`progress_state_machine=sii_monitoring.v1`. Their route is current dataset →
load active baseline → compare → reason → evidence → observations. These
states and labels are never reused by baseline construction.

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

## API

`POST /api/data/upload`

Multipart fields:

- `file`: CSV, TXT, or JSON telemetry.
- `workflow`: `create_baseline`, `analyze_new_data`, or `extend_baseline`.
- `approval_required`: optional boolean override for baseline workflows.

Baseline endpoints:

- `GET /api/data/baselines`
- `GET /api/data/baselines/jobs/{job_id}`
- `GET /api/data/baselines/candidates/{model_id}`
- `POST /api/data/baselines/candidates/{model_id}/approve`

Every baseline status and result publishes `sii_engine_invoked: false`.
Automated tests monkeypatch the SII runner to fail if either baseline workflow
reaches it.
