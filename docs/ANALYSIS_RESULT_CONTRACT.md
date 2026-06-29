# Analysis Result Contract

Neraium analysis endpoints expose one canonical `AnalysisResult` object at `analysis_result`.
Legacy fields can remain for compatibility, but frontend rendering should prefer this contract.

## Schema

Required top-level fields:

- `analysis_id`: stable id for this analysis run.
- `upload_id`: id of the uploaded telemetry source.
- `source_file`: uploaded CSV filename.
- `generated_at`: ISO timestamp when the contract was generated.
- `data_quality`: upload readiness, warning, integrity, and normalized telemetry summary.
- `executive_summary`: short operator summary for the Overview screen.
- `systems[]`: detected systems or telemetry groups with evidence-backed changes.
- `relationships[]`: relationship graph edges with strength, confidence, deltas, window, and evidence refs.
- `fingerprint`: baseline/current behavior summary, drift status, confidence, deviations, explanation, and evidence refs.
- `insights[]`: evidence-backed findings only.
- `recommendations[]`: evidence-backed operator checks only.
- `evidence_index`: reusable evidence objects keyed by `evidence_id`.
- `warnings[]`: safe display warnings.
- `errors[]`: failed-state errors.

Empty, processing, missing, and failed states must still return this shape with empty arrays and a `status` such as `empty`, `processing`, `missing`, or `failed`.

## Evidence Model

Every evidence item is stored once in `evidence_index`:

- `evidence_id`
- `type`
- `description`
- `source_tags`
- `metric_delta`
- `relationship_delta`
- `time_window`
- `confidence`
- `calculation_method`

`insights`, `relationships`, `fingerprint`, and `recommendations` reference evidence by id through `evidence_refs`.
The frontend must resolve refs through `evidence_index`; it should not display findings whose refs do not resolve.

## Normalized Telemetry

The normalized telemetry layer is built from the already parsed upload rows. It does not re-read the CSV.
Each normalized record contains:

- `timestamp`
- `tag_name`
- `value`
- `unit`
- `source_column`
- `quality`
- `missing_value_flags`
- `sampling_interval`
- `detected_metric_type`

The public contract includes a bounded `records` sample plus tag summaries so large uploads do not inflate result payloads.

## Relationship Graph

Canonical `relationships[]` contains changed relationship edges derived from telemetry windows:

- `source`
- `target`
- `relationship_type`
- `strength`
- `confidence`
- `baseline_strength`
- `current_strength`
- `change_percent`
- `supporting_metrics`
- `time_window`
- `evidence_refs`

Relationship strength is currently based on baseline/current correlation deltas from uploaded CSV telemetry.

## Fingerprint Model

`fingerprint` summarizes:

- normal operating behavior
- current behavior
- drift status
- largest deviations
- confidence and confidence score
- supporting evidence refs
- plain-language explanation

Fingerprint evidence must include at least the baseline/current window context and any metric or relationship deviations used in the explanation.

## Frontend Usage Rules

- Overview renders `executive_summary` only for completed analysis.
- Insights render insight explanation plus resolved evidence.
- Systems render `systems[]` and relationship changes.
- Fingerprint renders drift explanation, confidence, and resolved evidence.
- More renders data quality, source file, warnings, errors, and analysis metadata.
- Never render placeholder findings, generic pending-verification text, demo systems, fake recommendations, or stale previous analysis as the current result.
- If a field is unavailable, hide it instead of showing placeholder copy.
