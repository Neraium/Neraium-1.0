# SII Math Stack Implementation Plan

## Purpose
Implement a generalized Systemic Infrastructure Intelligence (SII) stack where every uploaded/streamed dataset is processed as time-series system behavior, and outputs always include:

1. Emerging instability
2. Affected system
3. Contributing factors
4. Lead-time inference (derived)

## Canonical Instability Function

`I(t) = f(D, R, E, C, T)`

- `D`: state drift and trajectory pressure
- `R`: relationship degradation
- `E`: entropy growth / unpredictability
- `C`: causal evidence confidence
- `T`: topology propagation activation

## Layer-to-Code Mapping (Current + Target)

1. State Space (`x_t`)
   - Current: `backend/app/services/csv_parser.py`, `backend/app/services/data_quality.py`, `backend/app/services/upload_jobs.py`
   - Target: canonical feature matrix contract for CSV/JSON/stream inputs.
2. Dynamics (`dx/dt`, `d²x/dt²`)
   - Current: `backend/app/services/sii_runner.py` (`transition_pressure`, `velocity_history`)
   - Target: explicit derivative tensors persisted in replay frame metadata.
3. System Graph (`G=(V,E)`)
   - Current: `backend/app/engine/relationships.py`, `backend/app/services/structural_cognition.py`
   - Target: persisted graph snapshot per analysis run.
4. Information Flow (Mutual Information)
   - Current: partial proxy via relationship deltas.
   - Target: MI feature set between key channel pairs.
5. Entropy
   - Current: indirect via variability.
   - Target: rolling entropy metrics per subsystem.
6. Bayesian Updating
   - Current: confidence heuristics in `backend/app/services/sii_intelligence.py`.
   - Target: posterior confidence updates tied to evidence sequences.
7. Graph Signal Processing
   - Current: not explicit.
   - Target: propagation metrics over graph-local neighborhoods.
8. Spectral Analysis
   - Current: not explicit.
   - Target: dominant frequency/oscillation change indicators.
9. Dynamical Systems Stability
   - Current: regime transitions in `backend/app/services/sii_runner.py`.
   - Target: attractor-distance and recovery-basin scoring.
10. Network Stability
   - Current: not explicit.
   - Target: graph stability indicators (eigenvalue-derived risk features).

## Phase Rollout

### Phase 1 (Now): Foundation + Unified Output Contract
- Normalize input across CSV/JSON/stream.
- Ensure all upload analyses emit `instability_index` with component decomposition (`D,R,E,C,T`).
- Persist decomposition in runtime state + top-level intelligence payload.
- Keep replay and UI aligned on same run artifact.

### Phase 2: Information + Entropy + Bayesian Evidence
- Add MI and entropy calculators.
- Upgrade confidence from static heuristic to evidence-updating posterior.
- Add tests for early-warning lift vs threshold-only baseline.

### Phase 3: Graph/Spectral/Dynamics/Network Stability
- Add topology-propagation calculations, spectral indicators, and network stability metrics.
- Encode explanatory traces linking instability changes to observed subsystem behavior.

## Data Contracts (Required in Analysis Payload)

- `instability_index.score` (0..1)
- `instability_index.components.drift` (`D`)
- `instability_index.components.relationship_degradation` (`R`)
- `instability_index.components.entropy_growth` (`E`)
- `instability_index.components.causal_evidence` (`C`)
- `instability_index.components.topology_propagation` (`T`)
- `instability_index.model.version`
- `core_sii_outputs` (existing contract)

## Acceptance Tests

1. Upload replay parity
   - Upload CSV with timestamped drift sequence.
   - Confirm replay frames and main intelligence panel reference same run id and same `instability_index`.
2. Reset isolation
   - Reset runtime while old upload job is in-flight.
   - Confirm no pre-reset job can repopulate latest state.
3. Unknown system identity
   - Upload telemetry with unmapped semantics.
   - Confirm identity response is explicitly `unknown` with low confidence, not a hard domain claim.
4. Core output completeness
   - For CSV/JSON/stream path, assert required SII outputs and `instability_index` decomposition are present.

## Definition of Done

- All ingestion paths (CSV, JSON, live connector stream) run through shared SII decomposition path.
- Replay and intelligence views read the same persisted run payload.
- Core output contract is enforced in tests.
