# Unified SII Architecture

## Scope

Phase 1 established `backend/app/engine/sii_engine.py::evaluate_sii` as the single authoritative Systemic Infrastructure Intelligence (SII) entrypoint for uploaded telemetry. Phase 2 keeps that entrypoint and every Phase 1 compatibility calculation unchanged while adding focused graph-level, like-mode, elapsed-time persistence, multiscale, and empirical-threshold modules. Phase 3 adds downstream evaluation of externally configured engineering priors. Phase 4 adds persistent behavioral identity/memory, expected behavior, controlled learning, longitudinal graph/evolution/propagation evidence, events, immutable snapshots, and assumption-gated advanced mathematics. Transparent evidence fusion now preserves all Phase 1–4 sources. The entrypoint remains orchestration code.

Neraium is read-only and human-in-the-loop. The engine records persistent behavioral change and supporting evidence. It does not control equipment, diagnose root cause, prescribe repairs, assert causality, or predict an exact failure time. No generative-AI or LLM interpretation is part of the analytical engine.

Customer authority and repository research/reference boundaries are defined in [SII authority boundaries](SII_AUTHORITY_BOUNDARIES.md). The structural-cognition facade is not part of the default upload authority.

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
       -> configurable physics-informed reasoning
       -> infrastructure identity and active-model load
       -> expected behavior and persistent graph comparison
       -> behavioral evolution and candidate propagation paths
       -> assumption-gated spectral/dynamical/network indicators
       -> controlled baseline/model learning decision
       -> immutable model, baseline, snapshot, and event writes
       -> transparent Phase 1–4 evidence fusion
       -> canonical SII v2 contract
  -> legacy compatibility mapping
  -> presentation contracts and evidence persistence
```

The uploaded-telemetry implementation is:

1. `backend/app/services/upload_jobs.py` parses and profiles the upload.
2. `backend/app/services/upload_pipeline.py` performs upload-only normalization, constructs a compatibility-context callback, and calls `evaluate_sii` once.
3. `backend/app/engine/sii_engine.py` invokes the preserved Phase 1 components and isolated Phase 2 modules, evaluates configured Phase 3 priors, fuses evidence transparently, then returns one canonical result.
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
| Configurable engineering priors | `engine/sii/physics_reasoning.py` | Active Phase 3; generic declarative evaluation with explicit applicability |
| Transparent evidence organization | `engine/sii/evidence_fusion.py` | Active Phase 3; no weighting, voting, probability, or diagnosis |
| Behavioral storage contract | `engine/sii/behavioral_model_contract.py`, `behavioral_model_store.py` | Active Phase 4; storage-neutral, append-only, source-run-attributed |
| Behavioral identity and signal/relationship memory | `engine/sii/behavioral_model.py` | Active Phase 4; robust, inspectable, versioned |
| Persistent Behavioral Graph | `engine/sii/behavioral_graph.py` | Active Phase 4; current/active/snapshot/reference comparison, non-causal |
| Expected behavior | `engine/sii/expected_behavior.py` | Active Phase 4; transparent robust response models and empirical residual intervals |
| Controlled baseline evolution | `engine/sii/baseline_evolution.py` | Active Phase 4; explicit safeguards and optional human approval |
| Long-term behavioral evolution | `engine/sii/behavioral_evolution.py` | Active Phase 4; persistence/recovery/adaptation states without degradation claims |
| Propagation-aware analysis | `engine/sii/propagation_analysis.py` | Active Phase 4 when direction/lag/timing support exists; alternatives retained |
| Event memory | `engine/sii/event_memory.py` | Active Phase 4; external and telemetry-derived provenance separated |
| Optional advanced math | `engine/sii/spectral_analysis.py`, `dynamical_stability.py`, `network_stability.py` | Active Phase 4 with conservative assumption gates; limited otherwise |
| Bayesian evidence interface | `engine/sii/bayesian_evidence.py` | Present but inactive/deferred; posterior always null |
| Phase 4 coordinator | `engine/sii/phase4.py` | Active additive stage called once by `evaluate_sii` |

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
  "physics_reasoning": {},
  "physics_evidence": {},
  "propagation_analysis": {},
  "persistence_analysis": {},
  "evidence_fusion": {},
  "behavioral_model": {},
  "expected_behavior": {},
  "behavioral_evolution": {},
  "behavioral_snapshots": {},
  "event_memory": {},
  "spectral_analysis": {},
  "dynamical_stability": {},
  "network_stability": {},
  "bayesian_evidence": {},
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

### Active Phase 2 and Phase 3 sections

`relationship_graph`, `operating_modes.mode_conditioned_baseline`, `data_conditions.empirical_thresholds`, `persistence_analysis.adaptive_persistence`, and `multiscale_analysis` contain active Phase 2 supporting evidence. They are non-authoritative: they do not create or suppress compatibility findings, replace runner or temporal state, or alter frontend-visible severity. A Phase 2 module returns `limited` with an exact fallback reason when its timestamp, mode-feature, history, or pair-count minimum is not met. It never reports fallback evidence as a successful conditioned calculation.

`physics_reasoning` is an active Phase 3 section. `physics_evidence` is a backward-compatible alias. Priors come only from external configuration, and unmet applicability contributes no evidence. Phase 4 canonical sections are active and replace the former behavioral/propagation placeholders. Candidate paths require persistent graph, direction, lag, timing, mode, quality, health, multiscale, and strength support; unsupported and competing paths remain explicit. Evidence fusion preserves the full canonical payload from every present source module and never averages, weights, votes, estimates probability, or produces an engineering interpretation.

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

They are populated from `sii_result.compatibility`. This preserves frontend and evidence-persistence consumers while establishing the canonical source. Compatibility aliases named `projected_time_to_failure*` remain only inside internal canonical compatibility objects for older server-side consumers. Customer upload and runner projections omit them. New code must use the non-predictive `review_window*` fields.

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
- `phase_3_active` (currently `true`)
- `phase_3_effect` (currently `transparent_evidence_enrichment_only`)
- `engineering_priors_evaluated`
- `engineering_priors_applicable`
- `engineering_observations_generated`
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
- Phase 3: active and additive: externally configurable physics priors.
- Phase 4: active and additive: isolated persistent behavioral models, signal/relationship/mode/graph memory, expected behavior, controlled baseline evolution, snapshot evolution, candidate propagation context, event memory, immutable snapshots, deterministic confidence, optional advanced indicators, and transparent Phase 1–4 fusion.
- Bayesian posterior evidence: interface present but inactive/deferred; `posterior` remains null.

Phase 2 and Phase 3 evidence are additive to the canonical result. The legacy upload compatibility payload remains populated only from the preserved Phase 1 calculations, preventing silent frontend changes. Evidence records additionally persist a compact `phase_2_supporting_evidence` snapshot; it is labeled non-authoritative and does not replace existing evidence fields.

## Phase 4 Persistent Model Architecture

```text
explicit infrastructure identity + observed schema
  -> BehavioralModelStore.load_model(model_id)
  -> immutable active model + previous/long-term snapshots
  -> compare current Phase 1–3 evidence without mutation
       -> expected signal behavior and residuals
       -> persistent Behavioral Graph changes
       -> long-term behavioral evolution
       -> candidate propagation paths and alternatives
       -> optional spectral/dynamical/network indicators
  -> deterministic baseline-learning safeguards
       -> blocked/deferred/rejected: active model remains unchanged
       -> pending human validation: candidate baseline only
       -> accepted automatic: new model + active baseline version
  -> immutable snapshot
  -> provenance-separated events
  -> transparent Phase 1–4 evidence fusion
```

`BehavioralModelStore` defines `load_model`, `save_model`, `create_model`, snapshot create/load/list/restore, event append, learning-decision recording, relationship retirement, and candidate/active baseline operations. The runtime implementation stores an atomically merged, append-only per-model ledger using the existing `latest_payloads` repository. The in-memory implementation is contract-equivalent. No Phase 4 database-specific API leaks into the analytical modules, and no new runtime table/schema migration is needed.

Infrastructure identity includes organization, facility, system, subsystem, equipment group, configured model id, and an observed telemetry schema fingerprint as available. A configured model/system scope (or facility plus explicit subsystem/equipment group) is required. Unknown/conflicting identity never falls back to filename, room label, a default site, or another system’s memory.

## Controlled Learning and Immutability

Every learning decision retains its exact checks and evidence. The active model is not changed until current-run expected behavior, residuals, graph comparison, propagation, evolution, physics, multiscale, quality, health, and stability evidence have been evaluated. Candidate periods must meet history, mode, stability, relationship, model-validation, learning-delay, and active-observation safeguards.

Model saves create forward versions. Baseline candidates and activations are separate immutable records. Human-validation candidates are never activated automatically. Snapshots are immutable, deterministically comparable, source-run-attributed, linked to the previous snapshot, and include rollback references. Restore creates a new forward model version. Relationship retirement retains strength/change/lag/covariance/MI history.

## Phase 4 Failure Isolation and Status

- Inadequate/conflicting identity: Phase 4 `limited`, no model selected, no writes.
- Storage unavailable: Phase 4 `limited`, exact storage failure in trace, no silent learning; Phase 1–3 and fusion continue.
- Invalid expected model prerequisites: target result `limited`/unavailable; no expected value fabricated.
- Unsupported propagation segment: segment retained with exact reasons; no path/cause claim.
- Advanced mathematical assumption failure: module `limited`; core Phase 4 continues.
- Bayesian interface: `deferred`, `active: false`, `posterior: null`.
- Any optional module exception: visible as `failed` in its section/advanced-module trace; no hidden fallback conclusion.

## Read-only and Human-review Boundary

Phase 4 memory is an analytical reference, not a physical simulation or control twin. It records how telemetry behavior and associations evolve. The engine remains deterministic, explainable, evidence-based, read-only, and human-in-the-loop. It contains no LLM reasoning, generative conclusion, neural network, embedding, opaque ensemble, causal proof, root-cause diagnosis, failure/RUL prediction, maintenance recommendation, or operational control action.
