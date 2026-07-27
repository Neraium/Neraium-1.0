# SII Math Audit

## Audit state

Updated for unified SII Phase 1 on branch `agent/unified-sii-engine-phase-1`.

The authoritative uploaded-telemetry entrypoint is now:

```text
backend/app/engine/sii_engine.py::evaluate_sii
```

The upload pipeline calls it exactly once. The detailed formulas, constants, minimums, missing-value behavior, assumptions, and limitations are maintained in [sii_math_specification.md](sii_math_specification.md). This audit records execution paths, duplicate calculations, active/retained functions, and public consumers.

## Active execution path

```text
POST /api/data/upload or connector ingestion
  -> upload queue/runtime records
  -> upload_jobs._build_csv_result
  -> upload_pipeline.run_structural_analysis_pipeline
       -> upload-only normalization
       -> evaluate_sii exactly once
          -> build_baseline_analysis
          -> build_relationship_baseline
          -> assess/apply operating mode
          -> build data quality
          -> assess/apply sensor health
          -> assess_persistence
          -> evaluate_temporal_math
          -> run_sii_runner / BackendSiiRunner
       -> canonical sii_result
       -> compatibility mapping
       -> upload intelligence and presentation contracts
  -> final result, replay, evidence, and latest state persistence
```

Direct code and integration tests confirm `upload_pipeline` no longer invokes relationship analysis, temporal math, or the runner independently.

## Preserved analytical inventory

| Requested evidence | Active implementation | Canonical section | Audit result |
|---|---|---|---|
| Baseline signal drift | `services/baseline_analysis.py::build_baseline_analysis` | `signal_drift` | Preserved |
| Pearson relationships | `services/relationship_baselines.py::build_relationship_baseline` | `relationship_analysis`, `relationship_graph` | Preserved |
| Relationship classification | `_relationship_change_type` | relationship edges | Preserved |
| Relationship importance | `score_relationship_importance` | relationship edges | Preserved |
| Operating-mode assessment | `services/operating_modes.py` | `operating_modes` | Preserved and attached; not yet baseline conditioning |
| Sensor-health adjustment | `services/sensor_health.py` | `data_conditions`, enriched edges | Preserved |
| Telemetry-confidence adjustment | `services/telemetry_confidence.py` | compatibility intelligence | Preserved |
| Covariance | `services/sii_runner.py` | `covariance_analysis` | Preserved |
| Regularized Mahalanobis | `BackendSiiRunner.ingest` | covariance metrics | Preserved |
| Covariance shift | `BackendSiiRunner.ingest` | covariance metrics | Preserved |
| Drift velocity/acceleration/curvature | baseline and runner modules | signal/covariance sections | Preserved separately |
| Fixed persistence/accumulation | `engine.analysis.assess_persistence`, baseline score, runner gates | `persistence_analysis` | Preserved separately |
| Temporal state drift | `engine/temporal_math.py` | `temporal_analysis` | Newly connected to uploads; unchanged |
| Variance and entropy growth | temporal math | temporal analysis | Newly connected; unchanged |
| Correlation and MI drift | temporal math | temporal analysis | Newly connected; unchanged |
| Lag drift | temporal math | temporal analysis | Newly connected; unchanged |
| Regime detection | temporal math and runner regimes | temporal/covariance sections | Preserved separately |
| Topology-propagation scalar | temporal math | temporal analysis | Preserved; not claimed causal |
| Temporal accumulation/confidence/index | temporal math | temporal analysis | Preserved; confidence not probability |

No formula above was deleted, substituted, or fused with a conflicting formula. Where overlapping concepts exist, canonical sections preserve each implementation under its source module.

## Duplicate and overlapping calculations

The audit found these overlapping implementations:

1. Relationship calculations
   - Active upload graph: `services/relationship_baselines.py`, 70/30 split, paired counts, classification, importance ranking.
   - Legacy direct engine: `engine/relationships.py`, 20% endpoint windows and absolute delta threshold 0.5.
   - Resolution: active upload continues using the service implementation. Legacy code is retained but not called by the pipeline.

2. Signal/baseline drift
   - Baseline service compares an adaptive low-variability window with the latest window.
   - Upload room heuristics compare early/recent mean and variance for presentation urgency.
   - Runner fallback compares rolling baseline/recent vector means.
   - Temporal state drift uses baseline z-scores.
   - Resolution: no replacement. Canonical signal, covariance, and temporal sections identify the source.

3. Persistence
   - Baseline signal outside-tolerance fraction.
   - Fixed recent-row directional support at 70%.
   - Runner distance persistence plus accumulation.
   - Temporal active-indicator persistence.
   - Resolution: all four are exposed separately under `persistence_analysis`; adaptive elapsed-time persistence remains Phase 2.

4. Instability composites
   - Runner technical/fallback score.
   - Legacy runner presentation instability index.
   - Temporal instability index.
   - Resolution: all remain module-local. Cross-module evidence fusion is explicitly inactive until Phase 3.

5. Regime/operating context
   - Baseline variability regime.
   - Deterministic telemetry operating mode.
   - Runner score regime.
   - Temporal change-point regime.
   - Resolution: values remain separately named; none is presented as root cause.

## Input and baseline audit

- Upload cleaning still occurs before `evaluate_sii` and provides ordered accepted rows.
- The entrypoint accepts dictionary or matrix rows and creates both representations without re-reading the source.
- Baseline signal drift retains its adaptive low-variability row-window search.
- Relationships retain their 70/30 split and sampling bounds.
- Runner retains rolling baseline/recent vector windows.
- Temporal math retains its default 35% baseline split.
- Operating-mode assessment currently annotates relationship evidence only. Like-mode baseline selection is not active in Phase 1.
- Missing-value behavior remains module-specific and is documented rather than normalized into a new universal rule.

## Canonical schema audit

`evaluate_sii` returns all required sections. Future sections return structured limited results:

- Phase 2: multiscale analysis (and adaptive persistence nested in persistence).
- Phase 3: physics evidence, candidate propagation paths, evidence fusion.
- Phase 4: behavioral model.

Canonical findings remain empty in Phase 1. Existing presentation condition/finding generation continues through the compatibility contract and its existing evidence guards.

## Frontend consumers retained

Frontend code currently reads:

- `baseline_analysis.column_drift`, `relationship_drift`, `relationship_graph`;
- `relationship_model.relationship_graph.edges`;
- `data_quality` readiness, warnings, and integrity;
- `engine_result` completion and evidence;
- `sii_intelligence` state, confidence, relationships, rooms, and review window;
- `sii_runner_result` plus `processing_trace` diagnostics;
- `analysis_result` systems, conditions, relationships, fingerprint, insights, and evidence index.

Phase 1 preserves these top-level fields. The new canonical object is additive at `sii_result`.

## Evidence persistence consumers retained

`services/upload_evidence.py` and `services/analysis_result_contract.py` continue to use:

- relationship paired counts, deltas, source rows, time windows, and evidence refs;
- baseline column deltas and windows;
- data-quality warnings and confidence;
- intelligence state/persistence/review window;
- source timestamps and replay windows;
- analysis relationships, conditions, fingerprint, and findings.

Compatibility mapping is populated from the same canonical evaluation, so persistence does not initiate another analytical pass.

## Processing trace audit

The canonical trace records the required engine identity, module outcomes, rows, columns, operating modes, scales, and runtime. Upload-specific normalization/replay/completion fields are merged afterward. An optional module failure appears in both `modules_failed` and `uncertainty.module_failures`.

## Safety-language audit

- The relationship graph is non-causal.
- Lag and topology values are ordering/connectivity evidence only.
- Confidence scores are heuristic sufficiency/consistency values, not probability.
- No Phase 1 canonical finding diagnoses a cause or recommends a repair.
- Compatibility keys named `projected_time_to_failure*` contain the existing conditional review-window value and are deprecated. They are not a prediction of failure. New canonical and frontend work must prefer `review_window*`.
- No generative model is present in the analytical path.

## Validation evidence

Phase 1 adds:

- `tests/test_sii_engine_v2.py` for canonical numeric behavior, relationship weakening, spike suppression, sparse history, and failure isolation.
- `tests/test_sii_pipeline_unification.py` for exactly-once entrypoint invocation and compatibility equality.

Existing baseline, relationship, classification, sensor-health, telemetry-integrity, runner, temporal, upload, frontend-contract, and evidence tests remain the regression baseline. The full matrix and later-phase gates are in [sii_validation_plan.md](sii_validation_plan.md).
