# SII Math Stack Implementation Plan

> Historical roadmap note: this document predates the unified SII Phase 1 audit. Mutual-information and entropy evidence were activated in unified Phase 1. Unified Phase 2 statistical evidence, Phase 3 physics-informed reasoning/evidence fusion, and Phase 4 persistent behavioral memory are now active. Calibrated Bayesian posterior evidence remains deferred because the current engine does not have validated likelihoods, calibration data, reliability validation, acceptance approval, or an activated posterior implementation.

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
   - Current Phase 3: configured `confidence_modifier` values are preserved as descriptive prior metadata and explicitly are not applied or aggregated.
   - Current confidence must not be presented as a calibrated probability or causal posterior.
   - Deferred target: Bayesian posterior updates only after validated likelihood models, calibration data, and acceptance criteria exist.

7. Propagation-aware graph analysis
   - Current: `propagation_analysis.py` generates candidate paths only when timing, direction/lag, edge strength/stability, operating mode, health, quality, and historical support pass deterministic gates. Unsupported and competing paths remain visible and no cause is selected.
   - Limited: association-only relationships without validated direction and lag remain unsupported path segments.

8. Spectral Analysis
   - Current optional module: `spectral_analysis.py` reports dominant frequency/period, concentration, reference shifts, and oscillation emergence only with regular sampling, minimum duration/cycles, Hann windowing, Nyquist distance, and aliasing safeguards.
   - Limited: sparse, irregular, incomplete, constant, near-Nyquist, or short-cycle evidence returns `limited`.

9. Dynamical Systems Stability
   - Current optional module: `dynamical_stability.py` reports robust return-to-baseline timing and empirical trajectory/attractor-distance/transition-persistence proxies when history and timestamps support them.
   - Boundary: it makes no formal stability-theory result and no recovery-basin or failure claim.

10. Network Stability
    - Current optional module: `network_stability.py` reports structural scope, edge-weight sensitivity, neighborhood disruption, connectivity changes, and explicitly configured eigenvalue indicators when graph size is adequate.
    - Boundary: no network-risk score is produced.

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

### Unified Phase 3: Physics-Informed Reasoning and Transparent Evidence Fusion

Unified Phase 3 is complete and runs only after all Phase 2 analyses:

- `backend/app/engine/sii/physics_reasoning.py` evaluates externally configured, domain-specific engineering priors through a generic declarative condition language.
- Every prior checks equipment type, required telemetry, relationships, operating mode, prerequisites, validity, quality, health, and any configured historical-support condition before expected behavior is evaluated.
- Unmet applicability returns `not_applicable` with reasons and contributes no evidence.
- Applicable priors report supporting, contradictory, or indeterminate evidence with unchanged confidence-modifier metadata and complete source references.
- `backend/app/engine/sii/evidence_fusion.py` preserves all canonical source modules and classifies each item as supporting, limiting, contradictory, or neutral.
- Fusion generates deterministic behavioral observations with analytical uncertainty, evaluated and ignored priors, evidence references, and processing trace.
- Statistical evidence remains independent and authoritative. No score, vote, posterior, probability, diagnosis, prediction, remaining-life estimate, maintenance recommendation, or autonomous decision is generated.

The canonical engine version remains `neraium_sii/v2` for backward compatibility. `physics_reasoning` and `evidence_fusion` are additive, and the existing `physics_evidence` key remains as an alias of `physics_reasoning`.

### Unified Phase 4: Behavioral Digital Model and System Memory

Phase 4 is active inside the unified evaluation path after Phase 3 current-run evidence and before final fusion. It adds:

- explicit infrastructure identity and schema compatibility, with no memory attachment under unknown/conflicting identity;
- storage-neutral, append-only model, snapshot, event, decision, relationship-retirement, and baseline contracts;
- robust per-signal behavioral distributions, variability, trends, derivatives, temporal/multiscale context, quality/health history, and residual history;
- mode-separated relationship strength, information/covariance/lag histories, stability, volatility, persistence, graph context, configured-prior references, and full lifecycle;
- a persistent Behavioral Graph with current/active/previous/long-term/mode comparison and structural-change evidence;
- transparent, fixed-setting robust expected-response models and empirical residual intervals;
- explicit baseline gates and optional human approval without automatic activation;
- deterministic snapshot evolution/recovery/adaptation classifications;
- candidate propagation paths with unsupported segments and alternatives;
- provenance-separated event memory;
- complete confidence factor decomposition with `not_probability: true`;
- Phase 4 evidence sources added independently to transparent fusion.

The active model is never updated until current-run expected behavior, graph change, propagation, longitudinal evolution, and advanced evidence have completed and the baseline-learning decision passes. Unresolved residual/graph evidence is therefore not silently absorbed into normal behavior.

Phase 4 does not simulate the physical plant. It adds no neural model, embedding, generative reasoning, root-cause diagnosis, predictive-maintenance forecast, remaining-life estimate, maintenance recommendation, or control action.

### Phase 4 Mathematical Methods and Limits

Initial expected behavior uses deterministic Theil–Sen-style pairwise median slopes with median intercepts, fixed sampling bounds, validation by relative robust residual scale, and empirical 5th/95th residual offsets. Intervals are not probability intervals. Model selection is deterministic by mode, validation, support, and stable id ordering.

Signal distribution memory uses per-run medians, MAD-derived robust scales, and empirical quantiles. Historical summaries evolve by documented observation-count weighting because raw telemetry is not duplicated into the behavioral model. Relationship volatility is MAD-derived over stored strength history. These methods do not assume Gaussian data.

Compatibility summaries use an explicitly documented unweighted arithmetic mean of named, normalized evidence factors. Every factor is returned. The result is evidence compatibility—not a probability, likelihood, risk, diagnosis, or hidden score.

### Phase 4 Acceptance Coverage

Tests verify identity isolation, deterministic output from identical inputs/models, snapshot immutability, baseline and human-approval safeguards, health/quality no-update behavior, mode-separated relationships, traceable expected values/intervals, residual evidence without diagnosis, supported and ambiguous/competing propagation paths, external/derived event provenance, the full relationship lifecycle, independent fusion entries, storage-outage fallback, a null Bayesian posterior, advanced-module limited states, update ordering, and existing Phase 1–3 contracts.

### Deferred Bayesian Evidence

A Bayesian posterior is not active. Current confidence remains deterministic sufficiency and consistency evidence, not probability. Posterior evidence remains deferred until validated likelihoods, calibration datasets, and evaluation standards exist.

### Active Phase 4 Optional Mathematics

Propagation-aware graph paths and optional spectral, dynamical, and network indicators are active Phase 4 evidence modules. Each has explicit assumption gates and returns `limited` rather than synthetic evidence when support is inadequate. They do not control findings, create risk scores, assert formal stability, or establish causality.

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
- `physics_reasoning`
- `physics_evidence` (compatibility alias)
- `behavioral_model`
- `expected_behavior`
- `behavioral_evolution`
- `propagation_analysis`
- `behavioral_snapshots`
- `event_memory`
- `spectral_analysis`
- `dynamical_stability`
- `network_stability`
- `bayesian_evidence`
- `evidence_fusion`
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

11. Configurable engineering priors
    - Confirm the engine supplies no default domain rules.
    - Confirm every required prior field is validated and unmet applicability is recorded as `not_applicable`.
    - Confirm expected behavior is evaluated only from configured selectors and retains exact source references and observed values.

12. Transparent evidence fusion
    - Confirm all 12 Phase 1–3 input-module payloads and every present Phase 4 source payload remain independently present in the evidence inventory.
    - Confirm every evidence item has one allowed classification and retains origin, limitations, uncertainty, and trace.
    - Confirm observations expose evaluated/ignored priors and require human review.
    - Confirm no weighting, voting, probability, diagnosis, prediction, recommendation, or autonomous decision is produced.

## Definition of Done

- Every verified ingestion path runs through the shared `evaluate_sii` path exactly once.
- CSV is confirmed on the active upload path; JSON and live connector streams are only declared complete after direct execution-path and test verification.
- Replay, evidence, latest-upload state, compatibility output, and intelligence views read the same persisted run artifact.
- Canonical SII sections, uncertainty, processing trace, and compatibility contracts are enforced in tests.
- Phase 2 modules remain supporting evidence until an explicitly versioned contract makes them authoritative.
- Phase 3 physics-informed reasoning and transparent evidence fusion are active, additive, deterministic, and fully traceable.
- Canonical output contains active Phase 4 behavioral model, expected behavior, evolution, propagation, snapshots, events, optional advanced modules, and Bayesian-interface sections while preserving `physics_evidence` as a compatibility alias.
- Persistent behavioral memory is identity-isolated, append-only, versioned, snapshot-tested, and guarded against health/quality/instability learning.
- Bayesian posterior evidence remains inactive. Propagation, spectral, dynamical, and network modules are active only as assumption-gated, traceable Phase 4 evidence and return limited states when their assumptions fail.
