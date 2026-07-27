# SII Math Stack Implementation Plan

> Historical roadmap note: this document predates the unified SII Phase 1 audit. Mutual-information and entropy evidence were activated in unified Phase 1. The authoritative Phase 2 scope is maintained in `sii_architecture.md` and `sii_math_specification.md`; calibrated Bayesian posterior evidence remains deferred because the current engine does not have validated likelihoods or calibration data.

## Purpose
Implement a generalized Systemic Infrastructure Intelligence (SII) stack where uploaded telemetry is interpreted as time-series system behavior and produces evidence for:

1. Emerging instability
2. Affected system
3. Contributing factors
4. Derived lead-time context when the source time range supports it

The active production path must evaluate telemetry once through `backend/app/engine/sii_engine.py::evaluate_sii`. Supporting modules must contribute to the same canonical `neraium_sii/v2` result rather than creating a second analytical pass.

## Canonical Instability Function

`I(t) = f(D, R, E, C, T)`

- `D`: state drift and trajectory pressure
- `R`: relationship degradation
- `E`: entropy growth and reduced predictability
- `C`: deterministic evidence confidence based on data sufficiency, consistency, sensor health, and supporting observations; it is not causal proof or Bayesian probability
- `T`: topology-propagation activation or other graph-local propagation evidence when available

The decomposition remains a compatibility and roadmap model. Canonical SII evidence is also exposed through the named `sii_result` sections documented in `sii_math_specification.md` and `ANALYSIS_RESULT_CONTRACT.md`.

## Layer-to-Code Mapping (Current + Target)

1. State Space (`x_t`)
   - Current: parsed and normalized telemetry enters through `backend/app/services/csv_parser.py`, `backend/app/services/data_quality.py`, `backend/app/services/upload_jobs.py`, and `backend/app/services/upload_pipeline.py`.
   - Current canonical analysis input: `backend/app/engine/sii_inputs.py` and `backend/app/engine/sii_engine.py`.
   - Target: one verified feature-matrix contract shared by CSV, JSON, and connector-stream inputs.

2. Dynamics (`dx/dt`, `d²x/dt²`)
   - Current: temporal analysis includes trajectory, velocity, acceleration, curvature, transition pressure, covariance behavior, Mahalanobis-style deviation evidence, and persistence context where data coverage supports calculation.
   - Current modules include `backend/app/engine/temporal_math.py`, temporal modules orchestrated by `evaluate_sii`, and the wrapped covariance component in `backend/app/services/sii_runner.py`.
   - Target: persist bounded derivative and trajectory evidence in canonical run metadata and replay frames without duplicating the analytical path.

3. System Graph (`G=(V,E)`)
   - Current: `backend/app/engine/relationships.py`, `backend/app/engine/sii/relationship_graph.py`, `backend/app/services/structural_cognition.py`, and mode-conditioned relationship comparison orchestrated by `evaluate_sii`.
   - Current evidence includes baseline/current edge strength, relationship deltas, graph-level structural change, and supporting sample context.
   - Target: persist a bounded graph snapshot and explanatory edge trace per analysis run.

4. Information Flow (Mutual Information)
   - Current: mutual-information evidence is active temporal evidence and remains separately traceable from correlation-based relationship findings.
   - Target: expand MI coverage only where sample sufficiency, timestamp quality, and interpretability are adequate.

5. Entropy
   - Current: entropy evidence is active temporal evidence and is not merely a variability proxy.
   - Target: improve subsystem-level rolling entropy coverage while preserving explicit limits for sparse, irregular, or low-quality telemetry.

6. Evidence Confidence and Bayesian Updating
   - Current: confidence is deterministic sufficiency and consistency evidence informed by data quality, sensor health, operating mode, persistence, and module support.
   - Current confidence must not be presented as a calibrated probability or causal posterior.
   - Deferred target: Bayesian posterior updates only after validated likelihood models, calibration data, and acceptance criteria exist.

7. Graph Signal Processing
   - Current: graph-local structural evidence exists through relationship-graph analysis, but full signal propagation over graph neighborhoods is not yet authoritative.
   - Target: conservative propagation metrics with traceable source edges, activation paths, and uncertainty limits.

8. Spectral Analysis
   - Current: no authoritative spectral finding layer is documented in the unified SII contract.
   - Target: dominant-frequency, oscillation-shift, and periodic-instability indicators with adequate sampling and aliasing safeguards.

9. Dynamical Systems Stability
   - Current: regime and trajectory evidence is available through temporal and covariance analysis, with multiscale agreement used as supporting evidence.
   - Target: attractor-distance, recovery behavior, and recovery-basin scoring only where the data supports those interpretations.

10. Network Stability
    - Current: relationship-graph change is active supporting evidence; eigenvalue-derived network-risk scoring is not authoritative.
    - Target: graph stability indicators with explicit assumptions, sufficient graph size, and sensitivity checks.

## Phase Rollout

### Unified Phase 1: Foundation + Unified Output Contract

- Normalize parsed telemetry for canonical SII evaluation.
- Evaluate uploaded telemetry once through `evaluate_sii`.
- Emit canonical `neraium_sii/v2` evidence and preserve required compatibility fields.
- Activate mutual-information and entropy evidence as separately traceable temporal evidence.
- Persist canonical output, replay state, evidence records, and latest-upload state from the same run artifact.
- Keep replay and UI aligned to the same run id.

### Unified Phase 2: Conservative Supporting Evidence

Unified Phase 2 adds non-authoritative supporting analysis without independently controlling current `analysis_result` findings, state, severity, or confidence:

- empirical thresholds derived from available baseline evidence
- mode-conditioned and like-mode baseline selection
- graph-level relationship metrics and structural change evidence
- elapsed-time adaptive persistence with documented row-count fallback
- multiscale windows and cross-scale agreement or conflict
- temporal, covariance, mutual-information, and entropy evidence retained as separately traceable support

Phase 2 evidence may be exposed through canonical `sii_result` sections and `phase_2_supporting_evidence`. It must not create a second upload-side analytical pass or silently override compatibility-derived frontend findings.

### Deferred Bayesian Evidence

A Bayesian posterior is not active. Current confidence remains deterministic sufficiency and consistency evidence, not probability. Posterior evidence remains deferred until validated likelihoods, calibration datasets, and evaluation standards exist.

### Phase 3: Propagation, Spectral, Dynamics, and Network Stability

- Add topology-propagation calculations with explicit activation paths and uncertainty.
- Add spectral indicators with sampling-quality safeguards.
- Add recovery, attractor-distance, and network-stability metrics where telemetry and graph structure support them.
- Encode explanatory traces linking instability changes to observed subsystem behavior.

## Canonical SII Data Contract

The raw canonical engine object is exposed at top-level `sii_result` with engine identity `neraium_sii/v2`. Canonical sections include, as available:

- `data_conditions`
- `operating_modes`
- `signal_drift`
- `relationship_analysis`
- `relationship_graph`
- `covariance_analysis`
- `temporal_analysis`
- `multiscale_analysis`
- `persistence_analysis`
- `uncertainty`
- `processing_trace`

The frontend-oriented `analysis_result` contract is documented separately in `ANALYSIS_RESULT_CONTRACT.md`.

Compatibility payloads may continue to expose:

- `instability_index.score` (`0..1`)
- `instability_index.components.drift` (`D`)
- `instability_index.components.relationship_degradation` (`R`)
- `instability_index.components.entropy_growth` (`E`)
- `instability_index.components.causal_evidence` (`C`)
- `instability_index.components.topology_propagation` (`T`)
- `instability_index.model.version`
- `core_sii_outputs`

Clients must not infer a second analysis from compatibility fields. Canonical and compatibility views must reference the same analysis run.

## Acceptance Tests

1. Single canonical evaluation
   - Upload timestamped telemetry.
   - Confirm the upload pipeline invokes `evaluate_sii` exactly once.
   - Confirm no frontend, replay, evidence, or compatibility layer triggers another analytical pass.

2. Upload and replay parity
   - Upload a timestamped drift sequence.
   - Confirm replay frames, evidence records, latest-upload state, and the intelligence panel reference the same run id and canonical payload.

3. Reset isolation
   - Reset runtime while an older upload job is in flight.
   - Confirm no pre-reset job can repopulate latest state.

4. Unknown system identity
   - Upload telemetry with unmapped semantics.
   - Confirm identity is explicitly `unknown` or neutral with low confidence rather than a hard domain claim.

5. Canonical output completeness
   - For every verified ingestion path, assert required canonical SII sections, uncertainty, processing trace, and compatibility decomposition are present or return a structured limited state.

6. Processing trace integrity
   - Confirm attempted, completed, limited, and failed modules are recorded without hiding partial failures.
   - Confirm rows processed, operating modes used, scales used, and runtime metadata are bounded and internally consistent.

7. Mode-conditioned baseline behavior
   - Confirm like-mode comparison is selected when adequate matching history exists.
   - Confirm ambiguous or insufficient mode coverage returns a documented fallback rather than a fabricated exact match.

8. Adaptive persistence behavior
   - Confirm elapsed time is authoritative when timestamps are usable.
   - Confirm row-count fallback is explicit when timestamp quality is insufficient.
   - Confirm data quality, sensor health, and operating mode affect persistence requirements as documented.

9. Multiscale behavior
   - Confirm supported elapsed-time windows are evaluated when coverage exists.
   - Confirm unsupported scales return limited status rather than synthetic evidence.
   - Confirm cross-scale agreement and conflict are traceable.

10. Evidence persistence
    - Confirm canonical evidence, Phase 2 supporting evidence, and frontend evidence references are persisted from the same run artifact.
    - Confirm unresolved evidence references are not displayed as findings.

## Definition of Done

- Every verified ingestion path runs through the shared `evaluate_sii` path exactly once.
- CSV is confirmed on the active upload path; JSON and live connector streams are only declared complete after direct execution-path and test verification.
- Replay, evidence, latest-upload state, compatibility output, and intelligence views read the same persisted run artifact.
- Canonical SII sections, uncertainty, processing trace, and compatibility contracts are enforced in tests.
- Phase 2 modules remain supporting evidence until an explicitly versioned contract makes them authoritative.
- Deferred Bayesian, spectral, propagation, and network-stability claims are not presented as active capabilities before validation.