# Targeted reproducibility of four promoted observations

Completed: 2026-09-23T07:31:29.758281+00:00

Only windows 159 (NH4/NO3), 236, 248 and 251 (NO3/N2O) were evaluated. No production logic, configuration, thresholds, source values, baseline or window definitions were changed. Existing validation artifacts and headline claims were preserved.

## Protocol and comparison scope

The exact reference/comparison rows were reconstructed from normalized.csv using retained original source-row lists. Header and dictionary order match the original manifest. Both incoming states come from the immediately preceding original checkpoint, with state hashes and predecessor content hashes verified. Every call starts from a fresh detached copy of its original input; repetitions do not advance state. Dependencies and tracked production-file hashes were checked against the original freeze.

One worker made three calls per case (12 same-process repeats). Four additional workers each made one call in a new Python interpreter (4 fresh-process replays). Thread settings and PYTHONHASHSEED match the original run. Every full input, output, exception, comparison and execution log is retained under raw/promoted-repeat-runs/.

The **strict complete governed comparison** includes every field of analysis_result, relationship_graph and supplied_reference. A separately labeled **evidence comparison** excludes exactly analysis_result.generated_at and relationship_graph.runtime_seconds, which describe execution rather than the historical evidence. These exclusions were specified before any repeat ran. No other evidence, context, sufficiency, consequence or provenance field is removed. Full-response comparison removes nothing. All differences, including timestamps and timing, are preserved field-by-field.

## Results

Mode | Evidence matches (two execution fields excluded) | Strict complete governed matches | Strict full response matches | Original target promotion + governed flag reproduced
--- | ---: | ---: | ---: | ---:
same_process | 0/12 | 0/12 | 0/12 | 12/12
fresh_process | 0/4 | 0/4 | 0/4 | 4/4

Run | Window | Evidence match | Strict governed match | Full-response differing fields | Exception
--- | ---: | --- | --- | ---: | ---
fresh-159 | 159 | False | False | 127 | None
fresh-236 | 236 | False | False | 125 | None
fresh-248 | 248 | False | False | 125 | None
fresh-251 | 251 | False | False | 125 | None
same-159-1 | 159 | False | False | 127 | None
same-159-2 | 159 | False | False | 127 | None
same-159-3 | 159 | False | False | 127 | None
same-236-1 | 236 | False | False | 125 | None
same-236-2 | 236 | False | False | 125 | None
same-236-3 | 236 | False | False | 125 | None
same-248-1 | 248 | False | False | 125 | None
same-248-2 | 248 | False | False | 125 | None
same-248-3 | 248 | False | False | 125 | None
same-251-1 | 251 | False | False | 125 | None
same-251-2 | 251 | False | False | 125 | None
same-251-3 | 251 | False | False | 125 | None

## Field-level interpretation (no change to test criteria)

The declared comparison remains **0/12 same-process and 0/4 fresh-process evidence matches**, as well as zero strict complete governed matches. After excluding only the two prespecified execution fields, the remaining differences are execution-generation timestamps embedded in condition `activity_timeline` and `timeline` entries. Window 159 has four such differing fields per run; the other windows have two per run. Their original and replay values equal each response's own `analysis_result.generated_at`. These timestamps were not additionally excluded or repaired.

Read-only component comparisons of the preserved results found exact equality in every one of the 16 calls for:

- The complete target relationship graph edge, including identity, correlations, temporal and recurrence evidence, promotion, sufficiency, context, quality and sensor-health state.
- Complete governed SII evidence, every insight (including consequence and insight-level persistence), the entire evidence index, and analysis data quality.
- Supplied-reference provenance and both outgoing persistence/recurrence states.

Each listed component's original and replay hashes are identical; exact hashes are in `post_execution_component_diagnostics.per_run`. This does not convert the failed complete-output comparisons into passes. The original limitations, including insight persistence limited/false and consequence not quantifiable, reproduced unchanged.

Full unmodified responses additionally differ in generated run identifiers, timing fields, measured memory and performance-summary strings. The per-field listing below and companion JSON retain every occurrence. No other difference category was observed. There were no execution exceptions; numerical RuntimeWarnings in worker logs were preserved.

## Every observed discrepancy

The following list includes every distinct full-response difference path; counts are runs containing that difference. Exact original/replay values for every occurrence are in the companion JSON `runs[].comparison.full_response_differences` and per-run comparison files. No discrepancy was repaired.

- `/analysis_result/conditions/0/activity_timeline/2/time`: 16 runs.
- `/analysis_result/conditions/0/timeline/2/time`: 16 runs.
- `/analysis_result/conditions/1/activity_timeline/2/time`: 4 runs.
- `/analysis_result/conditions/1/timeline/2/time`: 4 runs.
- `/analysis_result/generated_at`: 16 runs.
- `/compatibility/sii_runner_result/latest_state/run_id`: 16 runs.
- `/compatibility/temporal_analysis/step_timings/correlation_drift`: 16 runs.
- `/compatibility/temporal_analysis/step_timings/entropy_growth`: 16 runs.
- `/compatibility/temporal_analysis/step_timings/evidence_confidence`: 16 runs.
- `/compatibility/temporal_analysis/step_timings/instability_decision`: 16 runs.
- `/compatibility/temporal_analysis/step_timings/lag_relationships`: 16 runs.
- `/compatibility/temporal_analysis/step_timings/lead_time`: 16 runs.
- `/compatibility/temporal_analysis/step_timings/mutual_information`: 16 runs.
- `/compatibility/temporal_analysis/step_timings/prepare_numeric_matrix`: 16 runs.
- `/compatibility/temporal_analysis/step_timings/rate_of_change`: 16 runs.
- `/compatibility/temporal_analysis/step_timings/regime_topology`: 16 runs.
- `/compatibility/temporal_analysis/step_timings/state_drift`: 16 runs.
- `/compatibility/temporal_analysis/step_timings/variance_growth`: 16 runs.
- `/covariance_analysis/latest_state/run_id`: 16 runs.
- `/covariance_analysis/runner_result/latest_state/run_id`: 16 runs.
- `/data_conditions/empirical_thresholds/runtime_seconds`: 16 runs.
- `/evidence_fusion/evidence_inventory/1/evidence/mode_conditioned_baseline/runtime_seconds`: 16 runs.
- `/evidence_fusion/evidence_inventory/2/evidence/mode_conditioned_baseline/runtime_seconds`: 16 runs.
- `/evidence_fusion/evidence_inventory/4/evidence/runtime_seconds`: 16 runs.
- `/evidence_fusion/evidence_inventory/5/evidence/step_timings/correlation_drift`: 16 runs.
- `/evidence_fusion/evidence_inventory/5/evidence/step_timings/entropy_growth`: 16 runs.
- `/evidence_fusion/evidence_inventory/5/evidence/step_timings/evidence_confidence`: 16 runs.
- `/evidence_fusion/evidence_inventory/5/evidence/step_timings/instability_decision`: 16 runs.
- `/evidence_fusion/evidence_inventory/5/evidence/step_timings/lag_relationships`: 16 runs.
- `/evidence_fusion/evidence_inventory/5/evidence/step_timings/lead_time`: 16 runs.
- `/evidence_fusion/evidence_inventory/5/evidence/step_timings/mutual_information`: 16 runs.
- `/evidence_fusion/evidence_inventory/5/evidence/step_timings/prepare_numeric_matrix`: 16 runs.
- `/evidence_fusion/evidence_inventory/5/evidence/step_timings/rate_of_change`: 16 runs.
- `/evidence_fusion/evidence_inventory/5/evidence/step_timings/regime_topology`: 16 runs.
- `/evidence_fusion/evidence_inventory/5/evidence/step_timings/state_drift`: 16 runs.
- `/evidence_fusion/evidence_inventory/5/evidence/step_timings/variance_growth`: 16 runs.
- `/evidence_fusion/evidence_inventory/6/evidence/runtime_seconds`: 16 runs.
- `/evidence_fusion/evidence_inventory/7/evidence/runtime_seconds`: 16 runs.
- `/evidence_fusion/evidence_inventory/8/evidence/latest_state/run_id`: 16 runs.
- `/evidence_fusion/evidence_inventory/8/evidence/runner_result/latest_state/run_id`: 16 runs.
- `/evidence_fusion/limiting_evidence/0/evidence/mode_conditioned_baseline/runtime_seconds`: 16 runs.
- `/evidence_fusion/neutral_evidence/1/evidence/mode_conditioned_baseline/runtime_seconds`: 16 runs.
- `/evidence_fusion/neutral_evidence/2/evidence/runtime_seconds`: 16 runs.
- `/evidence_fusion/neutral_evidence/3/evidence/step_timings/correlation_drift`: 16 runs.
- `/evidence_fusion/neutral_evidence/3/evidence/step_timings/entropy_growth`: 16 runs.
- `/evidence_fusion/neutral_evidence/3/evidence/step_timings/evidence_confidence`: 16 runs.
- `/evidence_fusion/neutral_evidence/3/evidence/step_timings/instability_decision`: 16 runs.
- `/evidence_fusion/neutral_evidence/3/evidence/step_timings/lag_relationships`: 16 runs.
- `/evidence_fusion/neutral_evidence/3/evidence/step_timings/lead_time`: 16 runs.
- `/evidence_fusion/neutral_evidence/3/evidence/step_timings/mutual_information`: 16 runs.
- `/evidence_fusion/neutral_evidence/3/evidence/step_timings/prepare_numeric_matrix`: 16 runs.
- `/evidence_fusion/neutral_evidence/3/evidence/step_timings/rate_of_change`: 16 runs.
- `/evidence_fusion/neutral_evidence/3/evidence/step_timings/regime_topology`: 16 runs.
- `/evidence_fusion/neutral_evidence/3/evidence/step_timings/state_drift`: 16 runs.
- `/evidence_fusion/neutral_evidence/3/evidence/step_timings/variance_growth`: 16 runs.
- `/evidence_fusion/neutral_evidence/4/evidence/runtime_seconds`: 16 runs.
- `/evidence_fusion/neutral_evidence/5/evidence/runtime_seconds`: 16 runs.
- `/evidence_fusion/neutral_evidence/6/evidence/latest_state/run_id`: 16 runs.
- `/evidence_fusion/neutral_evidence/6/evidence/runner_result/latest_state/run_id`: 16 runs.
- `/multiscale_analysis/runtime_seconds`: 16 runs.
- `/operating_modes/mode_conditioned_baseline/runtime_seconds`: 16 runs.
- `/persistence_analysis/adaptive_persistence/runtime_seconds`: 16 runs.
- `/processing_trace/performance/approximate_peak_memory_bytes`: 16 runs.
- `/processing_trace/performance/compact_summary/0`: 16 runs.
- `/processing_trace/performance/compact_summary/1`: 16 runs.
- `/processing_trace/performance/compact_summary/2`: 16 runs.
- `/processing_trace/performance/compact_summary/20`: 16 runs.
- `/processing_trace/performance/compact_summary/3`: 16 runs.
- `/processing_trace/performance/compact_summary/4`: 16 runs.
- `/processing_trace/performance/compact_summary/5`: 16 runs.
- `/processing_trace/performance/compact_summary/6`: 16 runs.
- `/processing_trace/performance/compact_summary/7`: 16 runs.
- `/processing_trace/performance/stages/0/cpu_seconds`: 16 runs.
- `/processing_trace/performance/stages/0/wall_seconds`: 16 runs.
- `/processing_trace/performance/stages/1/cpu_seconds`: 16 runs.
- `/processing_trace/performance/stages/1/wall_seconds`: 16 runs.
- `/processing_trace/performance/stages/10/cpu_seconds`: 16 runs.
- `/processing_trace/performance/stages/10/wall_seconds`: 16 runs.
- `/processing_trace/performance/stages/11/cpu_seconds`: 16 runs.
- `/processing_trace/performance/stages/11/wall_seconds`: 16 runs.
- `/processing_trace/performance/stages/12/cpu_seconds`: 16 runs.
- `/processing_trace/performance/stages/12/wall_seconds`: 16 runs.
- `/processing_trace/performance/stages/13/cpu_seconds`: 16 runs.
- `/processing_trace/performance/stages/13/wall_seconds`: 16 runs.
- `/processing_trace/performance/stages/14/cpu_seconds`: 16 runs.
- `/processing_trace/performance/stages/14/wall_seconds`: 16 runs.
- `/processing_trace/performance/stages/15/cpu_seconds`: 16 runs.
- `/processing_trace/performance/stages/15/wall_seconds`: 16 runs.
- `/processing_trace/performance/stages/16/cpu_seconds`: 16 runs.
- `/processing_trace/performance/stages/16/wall_seconds`: 16 runs.
- `/processing_trace/performance/stages/17/cpu_seconds`: 16 runs.
- `/processing_trace/performance/stages/17/wall_seconds`: 16 runs.
- `/processing_trace/performance/stages/18/cpu_seconds`: 16 runs.
- `/processing_trace/performance/stages/18/wall_seconds`: 16 runs.
- `/processing_trace/performance/stages/2/cpu_seconds`: 16 runs.
- `/processing_trace/performance/stages/2/wall_seconds`: 16 runs.
- `/processing_trace/performance/stages/3/cpu_seconds`: 16 runs.
- `/processing_trace/performance/stages/3/wall_seconds`: 16 runs.
- `/processing_trace/performance/stages/4/cpu_seconds`: 16 runs.
- `/processing_trace/performance/stages/4/wall_seconds`: 16 runs.
- `/processing_trace/performance/stages/5/cpu_seconds`: 16 runs.
- `/processing_trace/performance/stages/5/wall_seconds`: 16 runs.
- `/processing_trace/performance/stages/6/cpu_seconds`: 16 runs.
- `/processing_trace/performance/stages/6/wall_seconds`: 16 runs.
- `/processing_trace/performance/stages/7/cpu_seconds`: 16 runs.
- `/processing_trace/performance/stages/7/wall_seconds`: 16 runs.
- `/processing_trace/performance/stages/8/cpu_seconds`: 16 runs.
- `/processing_trace/performance/stages/8/wall_seconds`: 16 runs.
- `/processing_trace/performance/stages/9/cpu_seconds`: 16 runs.
- `/processing_trace/performance/stages/9/wall_seconds`: 16 runs.
- `/processing_trace/performance/total_cpu_seconds`: 16 runs.
- `/processing_trace/performance/total_wall_seconds`: 16 runs.
- `/processing_trace/total_runtime_seconds`: 16 runs.
- `/relationship_analysis/mode_conditioned_baseline/runtime_seconds`: 16 runs.
- `/relationship_graph/runtime_seconds`: 16 runs.
- `/temporal_analysis/step_timings/correlation_drift`: 16 runs.
- `/temporal_analysis/step_timings/entropy_growth`: 16 runs.
- `/temporal_analysis/step_timings/evidence_confidence`: 16 runs.
- `/temporal_analysis/step_timings/instability_decision`: 16 runs.
- `/temporal_analysis/step_timings/lag_relationships`: 16 runs.
- `/temporal_analysis/step_timings/lead_time`: 16 runs.
- `/temporal_analysis/step_timings/mutual_information`: 16 runs.
- `/temporal_analysis/step_timings/prepare_numeric_matrix`: 16 runs.
- `/temporal_analysis/step_timings/rate_of_change`: 16 runs.
- `/temporal_analysis/step_timings/regime_topology`: 16 runs.
- `/temporal_analysis/step_timings/state_drift`: 16 runs.
- `/temporal_analysis/step_timings/variance_growth`: 16 runs.

Full governed differences by run:

- fresh-159: /analysis_result/conditions/0/activity_timeline/2/time, /analysis_result/conditions/0/timeline/2/time, /analysis_result/conditions/1/activity_timeline/2/time, /analysis_result/conditions/1/timeline/2/time, /analysis_result/generated_at, /relationship_graph/runtime_seconds
- fresh-236: /analysis_result/conditions/0/activity_timeline/2/time, /analysis_result/conditions/0/timeline/2/time, /analysis_result/generated_at, /relationship_graph/runtime_seconds
- fresh-248: /analysis_result/conditions/0/activity_timeline/2/time, /analysis_result/conditions/0/timeline/2/time, /analysis_result/generated_at, /relationship_graph/runtime_seconds
- fresh-251: /analysis_result/conditions/0/activity_timeline/2/time, /analysis_result/conditions/0/timeline/2/time, /analysis_result/generated_at, /relationship_graph/runtime_seconds
- same-159-1: /analysis_result/conditions/0/activity_timeline/2/time, /analysis_result/conditions/0/timeline/2/time, /analysis_result/conditions/1/activity_timeline/2/time, /analysis_result/conditions/1/timeline/2/time, /analysis_result/generated_at, /relationship_graph/runtime_seconds
- same-159-2: /analysis_result/conditions/0/activity_timeline/2/time, /analysis_result/conditions/0/timeline/2/time, /analysis_result/conditions/1/activity_timeline/2/time, /analysis_result/conditions/1/timeline/2/time, /analysis_result/generated_at, /relationship_graph/runtime_seconds
- same-159-3: /analysis_result/conditions/0/activity_timeline/2/time, /analysis_result/conditions/0/timeline/2/time, /analysis_result/conditions/1/activity_timeline/2/time, /analysis_result/conditions/1/timeline/2/time, /analysis_result/generated_at, /relationship_graph/runtime_seconds
- same-236-1: /analysis_result/conditions/0/activity_timeline/2/time, /analysis_result/conditions/0/timeline/2/time, /analysis_result/generated_at, /relationship_graph/runtime_seconds
- same-236-2: /analysis_result/conditions/0/activity_timeline/2/time, /analysis_result/conditions/0/timeline/2/time, /analysis_result/generated_at, /relationship_graph/runtime_seconds
- same-236-3: /analysis_result/conditions/0/activity_timeline/2/time, /analysis_result/conditions/0/timeline/2/time, /analysis_result/generated_at, /relationship_graph/runtime_seconds
- same-248-1: /analysis_result/conditions/0/activity_timeline/2/time, /analysis_result/conditions/0/timeline/2/time, /analysis_result/generated_at, /relationship_graph/runtime_seconds
- same-248-2: /analysis_result/conditions/0/activity_timeline/2/time, /analysis_result/conditions/0/timeline/2/time, /analysis_result/generated_at, /relationship_graph/runtime_seconds
- same-248-3: /analysis_result/conditions/0/activity_timeline/2/time, /analysis_result/conditions/0/timeline/2/time, /analysis_result/generated_at, /relationship_graph/runtime_seconds
- same-251-1: /analysis_result/conditions/0/activity_timeline/2/time, /analysis_result/conditions/0/timeline/2/time, /analysis_result/generated_at, /relationship_graph/runtime_seconds
- same-251-2: /analysis_result/conditions/0/activity_timeline/2/time, /analysis_result/conditions/0/timeline/2/time, /analysis_result/generated_at, /relationship_graph/runtime_seconds
- same-251-3: /analysis_result/conditions/0/activity_timeline/2/time, /analysis_result/conditions/0/timeline/2/time, /analysis_result/generated_at, /relationship_graph/runtime_seconds

## Provenance and verification

`raw/promoted-repeat-runs/plan.json` was sealed before execution. It records comparison exclusions, original checkpoint hashes, input hashes, canonical column ordering, state handoffs, environment, dependency versions and runner hash. `input-<window>.json` retains each exact reconstructed call. `<run>.json.gz` preserves every run’s full input/output; `<run>-comparison.json` records hashes and all differences. `runner.py` preserves the executable test harness. The companion JSON contains artifact hashes and worker exit codes.

To reproduce in a separate fresh output location, preserve the original package and run the saved harness after adapting only its output directory; its overwrite guards intentionally prevent replacing this test. The execution command was the repository .venv Python running the retained runner with `--worker same-process` or `--worker fresh:<window>`, using the sealed environment. No existing evidence should be overwritten.

Verification:

```json
{
  "preexisting_artifacts_unchanged": true,
  "changed_artifacts": [],
  "production_unchanged": true,
  "production_changed": [],
  "source_unchanged": true,
  "preexisting_files_checked": 318,
  "all_inputs_unchanged": true,
  "all_four_original_promoted_states_reproduced": true
}
```

These results concern deterministic reproduction of saved evidence in the tested environment and source ordering. They do not validate physical events, attribution, context comparability or measurable consequence. Existing graph-versus-insight persistence distinctions remain unchanged.

Full-response discrepancy occurrence counts (a repeated field in another run counts again):

```json
{
  "condition timeline execution timestamp": 40,
  "analysis generation timestamp": 16,
  "generated run identifier": 112,
  "execution timing": 1680,
  "measured memory": 16,
  "performance summary string": 144
}
```
