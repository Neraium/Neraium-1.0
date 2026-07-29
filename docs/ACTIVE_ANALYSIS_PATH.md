# Active Analysis Path

Baseline construction is intentionally outside this path. Upload routing sends
`create_baseline` and `extend_baseline` to
`build_behavioral_baseline(...)`; only `analyze_new_data` (and the temporary
`legacy_analysis` compatibility value) enters the SII analysis orchestration.
See [Behavioral baseline workflows](BEHAVIORAL_BASELINE_WORKFLOWS.md).

This note records the active Neraium SII path after the legacy cleanup. The current product flow is:

1. Telemetry enters through `POST /api/data/upload` in `backend/app/routers/data.py`, or through the data connection poller in `backend/app/services/data_connections.py`.
2. Analysis uploads are recorded as queued evidence runs and queue jobs through `backend/app/services/runtime_db.py`, `backend/app/services/upload_jobs.py`, and `backend/app/services/evidence_store.py`. Baseline uploads create queue jobs but never evidence runs.
3. Analysis upload processing runs through `backend/app/services/upload_jobs.py` into `backend/app/services/upload_pipeline.py`; baseline uploads run through the dedicated `backend/app/services/behavioral_baseline.py` orchestration instead.
4. `upload_pipeline.py` performs upload-only normalization and calls `backend/app/engine/sii_engine.py::evaluate_sii` exactly once.
5. `evaluate_sii` orchestrates telemetry classification, signal drift, relationship baselines, operating context, data conditions, sensor health, empirical thresholds, mode-conditioned baselines, dynamic relationship-graph analysis, fixed persistence, adaptive elapsed-time persistence, temporal analysis, multiscale analysis, and covariance/runner analysis. After all Phase 2 analysis completes, it evaluates externally configured engineering priors through `physics_reasoning.py`. Phase 4 then resolves infrastructure identity, loads the storage-neutral Behavioral Digital Model, evaluates expected behavior, persistent-graph changes, longitudinal evolution, propagation context, and assumption-gated advanced mathematics, makes a controlled learning decision, and only then creates versioned model/baseline/snapshot/event records. `evidence_fusion.py` finally preserves Phase 1–4 source evidence without weighted scoring. The engine identity remains canonical `neraium_sii` v2. No phase diagnoses, predicts failure, recommends work, or controls infrastructure. `sii_runner.py` persists `latest_sii_state` through runtime DB/latest-payload storage as the wrapped covariance component.
6. Upload completion writes canonical result, summary, latest-upload state, replay, and evidence through `backend/app/services/upload_state_repository.py` and `backend/app/services/upload_evidence.py`; evidence records may include a bounded, explicitly non-authoritative `phase_2_supporting_evidence` snapshot.
7. `GET /api/data/latest-upload` resolves the canonical latest upload through `backend/app/services/latest_upload_state.py`.
8. `GET /api/facility/systems` returns systems only when a valid active upload/result exists. Before analysis it returns empty systems and empty intelligence status.
9. Frontend runtime state in `frontend/src/hooks/useFacilityRuntime.js` consumes latest-upload and facility-system APIs. It starts with no fallback systems and only displays systems returned by the backend.

## Active Modules

The active upload/analyze/dashboard path depends on these backend areas:

- `backend/app/routers/data.py`
- `backend/app/routers/facility.py`
- `backend/app/routers/evidence.py`
- `backend/app/services/upload_jobs.py`
- `backend/app/services/upload_pipeline.py`
- `backend/app/engine/sii_engine.py`
- `backend/app/engine/sii_contract.py`
- `backend/app/engine/sii_inputs.py`
- `backend/app/engine/temporal_math.py`
- `backend/app/engine/sii/empirical_thresholds.py`
- `backend/app/engine/sii/mode_conditioned_baseline.py`
- `backend/app/engine/sii/relationship_graph.py`
- `backend/app/engine/sii/adaptive_persistence.py`
- `backend/app/engine/sii/multiscale_analysis.py`
- `backend/app/engine/sii/physics_reasoning.py`
- `backend/app/engine/sii/evidence_fusion.py`
- `backend/app/engine/sii/behavioral_model_contract.py`
- `backend/app/engine/sii/behavioral_model_store.py`
- `backend/app/engine/sii/behavioral_model.py`
- `backend/app/engine/sii/behavioral_graph.py`
- `backend/app/engine/sii/expected_behavior.py`
- `backend/app/engine/sii/baseline_evolution.py`
- `backend/app/engine/sii/behavioral_evolution.py`
- `backend/app/engine/sii/propagation_analysis.py`
- `backend/app/engine/sii/event_memory.py`
- `backend/app/engine/sii/spectral_analysis.py`
- `backend/app/engine/sii/dynamical_stability.py`
- `backend/app/engine/sii/network_stability.py`
- `backend/app/engine/sii/bayesian_evidence.py`
- `backend/app/engine/sii/phase4.py`
- `backend/app/services/baseline_analysis.py`
- `backend/app/services/relationship_baselines.py`
- `backend/app/services/operating_modes.py`
- `backend/app/services/sensor_health.py`
- `backend/app/services/sii_runner.py`
- `backend/app/services/sii_intelligence.py`
- `backend/app/services/structural_cognition.py`
- `backend/app/services/upload_state_repository.py`
- `backend/app/services/upload_evidence.py`
- `backend/app/services/latest_upload_state.py`
- `backend/app/services/system_interpretation.py`
- `backend/app/services/evidence_store.py`

The active frontend consumption path is:

- `frontend/src/App.jsx`
- `frontend/src/components/AppWorkspaceRouter.jsx`
- `frontend/src/components/EngineeringReasoningWorkspace.jsx`
- `frontend/src/components/DataConnectionsWorkspace.jsx`
- `frontend/src/hooks/useFacilityRuntime.js`
- `frontend/src/services/api/uploadApi.js`
- `frontend/src/services/api/systemApi.js`

## Dependency Audit Result

Confirmed-dead files removed in this cleanup had no active app imports, no API-route dependency, no frontend dependency, and no current test dependency. The removed set was:

- `backend/demo/*`
- `backend/embedded/*`
- `backend/neraium_core/*`
- `backend/run_local_monolith.py`
- `backend/interoperability/sii_event_schema.py`
- `backend/interoperability/sii_import_adapters.py`
- `legacy/upload-replay-v1/*`
- `backend/safety/read_only_guard.py` (abandoned utility; no imports or runtime boundary calls)

Verification checks used before removal:

- Direct module/file-name search across backend, frontend, tests, scripts, docs, and CI files.
- Mounted route review from `backend/app/main.py`.
- Active upload execution path review from `backend/app/routers/data.py`, `backend/app/services/upload_jobs.py`, `backend/app/services/upload_pipeline.py`, and `backend/app/services/sii_runner.py`.
- Top-level backend package import scan confirming other SII-adjacent packages remain reachable through mounted routes, `structural_cognition`, or current tests.

The current replay route keeps explicit `mode=demo` and `mode=aquatic_demo` synthetic responses inside `backend/app/routers/replay.py` for compatibility tests, but production live replay does not fall back to these synthetic payloads.

## Do Not Reintroduce

Do not reintroduce a second SII engine, FD004 validation runner, monolith runner, embedded cognition shim, demo replay package, or legacy upload/replay router into the production import path. New analysis work should add a focused analytical module orchestrated by `evaluate_sii`, or return a structured limited state until real telemetry-backed analysis exists. It must not add a second upload-side analytical call path.

Engineering rules must remain external configuration supplied as `config.physics_reasoning_config.priors` (or the compatibility alias `config.engineering_priors`). The engine may evaluate only the declared source path, filter, operator, expected value, and logic. It must not add implicit domain rules, diagnostic interpretations, evidence weights, probability estimates, or maintenance actions. A prior with unmet equipment, signal, relationship, operating-mode, prerequisite, validity, health, quality, or historical-support conditions is recorded as `not_applicable` and contributes no engineering evidence.

Do not show facility systems before analysis. Avoid hardcoded commercial pool or `Source / Intake` labels in active UI or API responses; systems should come from active analysis state and neutral domain profiles.

## Active Phase 4 Memory Path

Phase 4 is an additive stage inside `evaluate_sii`; it is not a second analytical pipeline. Its ordering is enforced and tested:

1. Phase 1–3 current-run evidence completes.
2. Infrastructure identity is resolved from explicitly available organization, facility, system, subsystem, equipment-group, configured-model, and observed-schema identifiers.
3. The active model and immutable snapshots are loaded through `BehavioralModelStore`.
4. Expected signal behavior, persistent graph comparison, longitudinal change, candidate propagation paths, and optional advanced modules are evaluated against the unchanged active reference.
5. `baseline_evolution.py` records one explicit learning decision. Unresolved observations, poor data, unhealthy sensors, ambiguous mode, contradictory configured physics evidence, instability, failed model validation, or insufficient history prevent learning.
6. Accepted automatic updates create a new model version, candidate/active baseline record, and immutable snapshot. A human-validation policy stores only a pending candidate baseline and leaves the active baseline and model unchanged.
7. External and telemetry-derived events are stored with distinct provenance.
8. Phase 4 sections enter transparent evidence fusion with complete source payloads and classifications.

The default production adapter is `RuntimeBehavioralModelStore`. It stores a per-model append-only ledger through the existing `latest_payloads` repository and atomic mutation convention; no new database table is required. `InMemoryBehavioralModelStore` supplies the same contract for tests. Stored model versions, snapshots, events, decisions, candidates, activations, and relationship retirement history are immutable. Snapshot restoration creates a forward model version rather than overwriting history.

Identity is a hard isolation boundary. Unknown, ambiguous, or conflicting identity returns `behavioral_model.status: limited`, does not select an arbitrary model, and performs no behavioral-memory write. A storage outage likewise returns limited Phase 4 sections while Phase 1–3 and evidence fusion continue.

## Capability Status and Human Boundary

Active and tested Phase 4 capabilities are behavioral identity, signal memory, mode-separated relationship memory and lifecycle, persistent Behavioral Graph comparison, transparent expected-behavior models, residual evidence, controlled baseline evolution, snapshot comparison, candidate propagation paths, event memory, deterministic confidence decomposition, immutable snapshots, rollback references, and Phase 4 evidence-fusion inputs.

Spectral, dynamical-stability, and network-stability modules are active as optional evidence modules. They return `limited` when sampling, duration, timestamp, graph-size, or other assumptions fail. Their outputs are indicators/proxies only; they do not produce risk scores or formal stability claims.

`bayesian_evidence.py` is a future-facing interface only. Its normal result is `status: deferred`, `active: false`, and `posterior: null`. Even complete-looking configuration cannot activate a posterior until a validated update implementation, registered likelihoods, calibration data, reliability analysis, validation metrics, versioned parameters, and acceptance approval all exist.

Human review remains authoritative. The engine does not fabricate maintenance/validation events, infer root cause, predict failure or remaining life, recommend maintenance, or issue control actions.
