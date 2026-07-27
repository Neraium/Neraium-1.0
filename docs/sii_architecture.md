# Unified SII Architecture

## Scope

Phase 1 established `backend/app/engine/sii_engine.py::evaluate_sii` as the single authoritative Systemic Infrastructure Intelligence (SII) entrypoint for uploaded telemetry. Phase 2 keeps that entrypoint and every Phase 1 compatibility calculation unchanged while adding focused graph-level, like-mode, elapsed-time persistence, multiscale, and empirical-threshold modules. The entrypoint remains orchestration code.

Neraium is read-only and human-in-the-loop. The engine records persistent behavioral change and supporting evidence. It does not control equipment, diagnose root cause, prescribe repairs, assert causality, or predict an exact failure time. No generative-AI or LLM interpretation is part of the analytical engine.

## Authoritative call path

```text
upload/API or future live adapter
  -> input cleaning and normalization
  -> evaluate_sii(...) exactly once
       -> signal drift
       -> Pearson relationship analysis and graph
       -> deterministic operating-mode assessment
       -> data-quality and sensor-health context
       -> baseline-only empirical thresholds
       -> like-mode historical selection
       -> graph-level relationship metrics
       -> fixed and elapsed-time persistence views
       -> temporal math engine
       -> elapsed-time multiscale windows
       -> regularized covariance/Mahalanobis runner
       -> canonical SII v2 contract
  -> legacy compatibility mapping
  -> presentation contracts and evidence persistence
```

The uploaded-telemetry implementation is:

1. `backend/app/services/upload_jobs.py` parses and profiles the upload.
2. `backend/app/services/upload_pipeline.py` performs upload-only normalization, constructs a compatibility-context callback, and calls `evaluate_sii` once.
3. `backend/app/engine/sii_engine.py` invokes the preserved Phase 1 components and the isolated Phase 2 modules, then returns one canonical result.
4. The pipeline maps `sii_result.compatibility` into the unchanged top-level upload fields used by the frontend and evidence persistence.
5. `backend/app/services/analysis_result_contract.py` and `backend/app/services/upload_evidence.py` continue to build and persist public evidence contracts.

A future live adapter should prepare the same arguments and call `evaluate_sii`; it must not call the component engines independently.

## Module boundaries

| Responsibility | Implementation | Disposition |
|---|---|---|
| Canonical orchestration | `engine/sii_engine.py` | New authoritative entrypoint |
| Canonical status and compatibility sections | `engine/sii_contract.py` | New; no analytical formulas |
| Input shape and data-condition assembly | `engine/sii_inputs.py` | New; delegates quality scoring |
| Signal drift and cumulative-counter deltas | `services/baseline_analysis.py`, `services/cumulative_counters.py` | Wrapped unchanged |
| Pearson relationships and ranking | `services/relationship_baselines.py` | Wrapped unchanged |
| Operating-mode context | `services/operating_modes.py` | Wrapped unchanged |
| Sensor health and confidence ceilings | `services/sensor_health.py`, `services/telemetry_confidence.py` | Wrapped unchanged |
| Fixed row-support persistence | `engine/analysis.py` | Wrapped unchanged |
| Temporal state/variance/entropy/MI/lag/regime evidence | `engine/temporal_math.py` | Newly activated for uploads; formulas unchanged |
| Covariance, Mahalanobis, motion, and accumulation gates | `services/sii_runner.py` | Wrapped unchanged |
| Upload intelligence and public analysis contract | `services/sii_intelligence.py`, `services/analysis_result_contract.py` | Retained compatibility/presentation layer |
| Evidence persistence | `services/upload_evidence.py`, `services/evidence_store.py` | Retained; compact Phase 2 supporting evidence is additive |
| Baseline-only empirical thresholds | `engine/sii/empirical_thresholds.py` | Active Phase 2 supporting evidence; fixed-floor fallback is explicit |
| Like-mode historical selection | `engine/sii/mode_conditioned_baseline.py` | Active Phase 2 supporting evidence; global fallback is explicit |
| Dynamic relationship-graph metrics | `engine/sii/relationship_graph.py` | Active Phase 2 supporting evidence; non-causal |
| Elapsed-time persistence | `engine/sii/adaptive_persistence.py` | Active Phase 2 supporting evidence; row fallback is explicit |
| Timestamp-horizon comparisons | `engine/sii/multiscale_analysis.py` | Active Phase 2 supporting evidence; unsupported horizons remain limited |

`engine/relationships.py` remains a legacy direct engine component but is no longer invoked independently by the upload pipeline. Its formulas were not deleted. The active upload Pearson implementation remains `services/relationship_baselines.py`.

## Canonical result

The canonical object is stored at upload-result key `sii_result` and returned directly by `evaluate_sii`:

```json
{
  "engine": {"name": "neraium_sii", "version": "v2"},
  "status": "complete | limited | failed",
  "data_conditions": {},
  "operating_modes": {},
  "signal_drift": {},
  "relationship_analysis": {},
  "relationship_graph": {},
  "covariance_analysis": {},
  "temporal_analysis": {},
  "multiscale_analysis": {},
  "physics_evidence": {},
  "propagation_analysis": {},
  "persistence_analysis": {},
  "evidence_fusion": {},
  "behavioral_model": {},
  "findings": [],
  "uncertainty": {},
  "processing_trace": {},
  "compatibility": {}
}
```

### Status rules

- `complete`: the component ran and met its current minimum requirements.
- `limited`: the component could not meet minimum history/feature requirements, or a future-phase capability is deliberately inactive.
- `failed`: the component raised an exception. The exception type and message are recorded without aborting other optional modules.

The overall status is `failed` only when there are no usable rows or every core analytical component failed. An optional component failure produces an overall `limited` result while other evidence is preserved.

### Active supporting Phase 2 sections and later placeholders

`relationship_graph`, `operating_modes.mode_conditioned_baseline`, `data_conditions.empirical_thresholds`, `persistence_analysis.adaptive_persistence`, and `multiscale_analysis` contain active Phase 2 supporting evidence. They are non-authoritative: they do not create or suppress compatibility findings, replace runner or temporal state, or alter frontend-visible severity. A Phase 2 module returns `limited` with an exact fallback reason when its timestamp, mode-feature, history, or pair-count minimum is not met. It never reports fallback evidence as a successful conditioned calculation.

`physics_evidence`, `propagation_analysis`, `evidence_fusion`, and `behavioral_model` remain structured later-phase placeholders. Temporal math's existing `topology_propagation` scalar remains available inside `temporal_analysis`; Phase 3 candidate path analysis is not active. Existing runner and temporal composite scores remain separate; Phase 3 fusion is not emulated by averaging them.

## Compatibility contract

Phase 1 keeps these public upload fields unchanged:

- `baseline_analysis`
- `relationship_model`
- `engine_result`
- `data_quality`
- `sii_intelligence`
- `sii_runner_result`
- `processing_trace`
- `operating_state`
- `drift_status`

They are populated from `sii_result.compatibility`. This preserves frontend and evidence-persistence consumers while establishing the canonical source. Compatibility aliases named `projected_time_to_failure*` remain only because older clients expect the keys; their values are the existing conditional engineering-review window, not a failure-time prediction. New code must use `review_window*`.

## Processing trace

Every evaluation records:

- `sii_engine_called`
- `sii_engine_version`
- `modules_attempted`
- `modules_completed`
- `modules_limited`
- `modules_failed`
- `module_statuses`
- `module_failures`
- `phase_2_authoritative` (currently `false`)
- `phase_2_effect` (currently `supporting_evidence_only`)
- `rows_received`
- `rows_used`
- `columns_used`
- `operating_modes_used`
- `scales_used`
- `total_runtime_seconds`

The upload pipeline adds replay, normalization, population/sample, and completion metadata without rerunning any analytical module. For bounded runtime, the upload adapter configures the temporal component to use the latest 2,048 usable rows; direct callers retain the temporal component default of 5,000 unless configured. The temporal section reports its actual baseline and active counts.

## Failure isolation

Each analytical call is isolated. A Phase 2 module failure, temporal failure, unavailable operating context, sparse relationship history, or covariance limitation remains visible in its section and in `uncertainty.module_failures`. Other modules continue. Canonical confidence fields describe deterministic sufficiency or consistency; they are not probabilities.

## Phase boundaries

- Phase 1: active and preserved: unified entrypoint, original math, temporal integration, schema, compatibility, trace, tests, and documentation.
- Phase 2: active as supporting evidence, non-authoritative: graph-level metrics, exact like-mode historical selection, elapsed-time persistence, timestamp-horizon multiscale windows, and baseline-only empirical thresholds.
- Phase 3: planned: configurable physics priors, candidate propagation paths, transparent evidence fusion.
- Phase 4: planned: auditable behavioral digital model and calibration tooling.

Phase 2 evidence is additive to the canonical result. The legacy upload compatibility payload remains populated only from the preserved Phase 1 calculations, preventing silent frontend changes. Evidence records additionally persist a compact `phase_2_supporting_evidence` snapshot; it is labeled non-authoritative and does not replace existing evidence fields.
