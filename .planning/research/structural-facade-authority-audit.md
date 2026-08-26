# Structural-facade authority audit

> Question: Can the structural-cognition facade be removed from default customer/upload authority without changing qualified SII findings or overlapping P0.1?
> Date: 2026-08-26
> Target revision: `25e217e843ec845fb81e0190ce350812c21d6f01`
> Confidence: high for the default upload path and unsupported-claim findings; medium for the intended long-term status of legacy cognition/reference endpoints.

## Executive finding

Yes, with a narrow authority separation rather than deletion of the research packages. The normal historical upload eagerly calls `build_structural_cognition` from `build_upload_intelligence` and spreads every returned field into `sii_intelligence`. The facade does not influence formal finding classification. It does, however, alter customer explanation by prepending `operator_explanation_v2.summary`, and its full output is persisted/transported with the upload.

The facade contains unsupported customer-authoritative causality, counterfactual/probability, synthetic multi-facility/site, persistent-memory, twin, simulation, federation/exchange, training, certification and static-reference claims. The evidence-qualified upload status, relationship evidence, persistence, data/context limitations, scope/lineage and final upload replay are separate and must remain.

The complete field/consumer disposition is in `structural-facade-consumer-map.md`.

## Audit source and revision check

The requested current-audit artifacts were absent from this dedicated worktree. They were read without modification from `/home/ubuntu/Neraium-1.0-sii-audit-current/.planning/research/`:

- `sii-current-power-efficiency-audit.md`
- `sii-current-architecture-inventory.md`
- `sii-audit-delta-vs-pr107.md`

They were authored against `519be2c59f22b52fb4affe33297fffc942be09ef`. The target is `25e217e843ec845fb81e0190ce350812c21d6f01`; the only intervening code is PR #108 Health Relevance. `git diff 519be2c..25e217e` shows no changes to the traced facade, upload, frontend, or prior test files. Health Relevance is out of scope and untouched.

## Special Phase 1 reviews

### Structural causality and propagation

No approved causal evidence contract supports the facade's customer-facing claims.

- `StructuralCausalityEngine` labels the attribution category as a source and assigns fixed source pressure `0.72`.
- It directs drift edges from that assumed source to signals.
- Relationship direction is inferred from signal names: airflow/humidity becomes `airflow_to_moisture`; temperature/thermal becomes `thermal_to_environment`; everything else becomes `structural_pressure_flow`.
- Its explanations state “is contributing pressure” and “is propagating” from those assumptions.
- `OperatorExplanationEngine` then states that structural pressure “is propagating,” that a driver is the “leading upstream contributor,” and that the continuation path suggests future behavior.

Sources: `backend/engines/structural_causality_engine.py:14-76,88-115`; `backend/explanations/operator_explanation_engine.py:17-68`.

Classification: `heuristic_capability_signaling`; non-authoritative for customer causality. Legitimate telemetry-derived relationship/path information remains available through `relationship_evidence`, `relationship_graph`, canonical `sii_result.relationship_analysis`, graph/propagation evidence, and the bounded SII evidence projection. Those facts must remain in Investigation using non-causal language.

### Counterfactuals

The counterfactual package is fixed heuristic arithmetic, not a validated causal/physical model.

- urgency selects fixed base day ranges;
- persistence count, facade propagation score, and static-memory acceleration subtract days;
- a “structural fragmentation probability band” is a weighted formula with fixed floors/caps;
- scenario summaries claim likely acceleration and fragmentation.

Source: `backend/engines/counterfactual_engine.py:16-53`.

Classification: `heuristic_capability_signaling`. Proposed disposition: remove from default customer authority; retain only behind an explicit internal/experimental boundary.

### Multi-facility and multi-site

The output does not represent learned behavior across distinct facilities or systems over time. `build_facility_samples` converts up to four rooms from the current upload into facilities named `facility-1` through `facility-4`; with no rooms it fabricates Facility Alpha and Facility Beta. Every sample receives slices of the same archetypes/paths/stability state. Multi-facility and multi-site engines then compare those samples and label similarities as recurring deterioration, cross-site patterns, and fleet-wide pressure.

Sources: `backend/app/services/structural_cognition.py:230-232,465-485`; `backend/cognition/multi_facility_cognition_engine.py`; `backend/cognition/multi_site_cognition_network.py:6-43`.

Classification: `heuristic_capability_signaling`. Proposed disposition: absent from customer-authoritative results; research code retained and explicitly synthetic.

The frontend test named “multi-site portfolio” is unrelated: it displays separate persisted evidence runs by `adaptive_site_key`, not the facade network. That legitimate portfolio behavior remains.

### Persistent cognition memory

The facade memory does not survive real analysis runs. `build_structural_cognition` constructs a new `PersistentCognitionGraphMemory()` on each call, appends one snapshot, queries only that in-memory list, serializes it, then loses the object. The related store helper explicitly reports `storage_mode: "in_memory_reference"`.

Sources: `backend/app/services/structural_cognition.py:328-343`; `backend/cognition_graph/persistent_graph_memory.py:48-124`; `backend/cognition_graph/graph_memory_store.py:6-11`.

Classification: `heuristic_capability_signaling`. It cannot be described as persistent or longitudinal customer memory. This conclusion does not apply to the separately persisted/scoped Phase 4 behavioral-model and behavioral-memory architecture, which Phase 2 must not modify.

### Structural memory

The other facade memory field is also not tenant/facility longitudinal memory. It compares the current upload fingerprint with three module-level hard-coded fingerprints describing cultivation-oriented propagation and intervention histories.

Source: `backend/engines/structural_memory_engine.py:49-89,92-164`.

Classification: `heuristic_capability_signaling`; retainable as a static/research analog matcher, not customer history.

### Behavioral twin

The “behavioral infrastructure twin” is an aggregate package, not an independently fitted and validated twin. `BehavioralTwinEngine.build_twin` copies facade replay frames, facility cognition, static memory matches, causal paths, recovery/time heuristics, simulation, ontology, benchmark and evidence replay into one dictionary. It has no fitting, parameter learning, validation set, persisted twin identity/state, or cross-run update.

Source: `backend/digital_twin/behavioral_twin_engine.py:6-40`.

Classification: `heuristic_capability_signaling`. Proposed disposition: remove the customer twin claim; retain the packaging code only as internal research. Do not substitute another marketing synonym.

### Projected time, probability of failure, and RUL

No survival, reliability, failure-probability or RUL model supports these labels.

- Upload `project_time_to_failure_hours` starts from fixed urgency hours and scales them with elevated/review/watch counts, corroboration, persistent-column count and attribution severity.
- Runner `project_time_to_failure_hours_from_state` uses a fixed urgency base multiplied by a weighted instability/drift/transition-pressure factor.
- The values are rendered as conditional review windows and copied into `projected_time_to_failure*` compatibility aliases.
- The facade counterfactual separately emits an arithmetic “fragmentation probability band”; it is not a probability of equipment failure but is still an unsupported probability claim.

Sources: `backend/app/services/sii_intelligence.py:571-605`; `backend/app/services/sii_runner.py:960-980`; `backend/app/services/upload_jobs.py:1671-1677`; `backend/engines/counterfactual_engine.py:16-53`.

Classification: review-window fields are `review_required`; projected-time aliases are `required_compatibility_field`; counterfactual probability is `heuristic_capability_signaling`.

Proposed disposition: preserve a neutral review-window concept only if approved as operational scheduling, explicitly state it is not predicted failure timing, and remove projected-time aliases from customer authority. If a verified internal consumer still needs aliases, keep them deprecated/internal and document the consumer.

### Static/reference assets

The facade rebuilds and embeds the following in every upload despite no upload-specific evidence:

- canonical deterioration library;
- cultivation domain pack (hard-coded even for generic uploads);
- SII reference architecture and contracts;
- structural ontology and ontology corpus;
- case studies;
- industry certification packs;
- SII standard;
- operational-language standard.

Ontology extension candidates, generated progression dataset, training package and structural search combine static material with facade state but remain research/experimental rather than customer evidence.

Classification: constants/reference packs are `static_reference`; generated packages are `research_experimental`. Proposed disposition: remove from each analysis payload and retain existing code/docs/routes as explicit static/internal resources. Do not build a new reference-service architecture.

### Replay

Two replay producers must not be conflated.

1. `build_structural_cognition` builds a 24-frame synthesized facade replay used by its benchmark, dataset, twin, training and search packages.
2. The upload pipeline separately builds an upload replay (or an explicit empty optional replay) and overwrites `sii_intelligence["replay_timeline"]`; the same object is placed at top-level `result["replay_timeline"]`.

Sources: `backend/app/services/structural_cognition.py:180-218,249-293,350-390`; `backend/app/services/upload_pipeline.py:347-384,415-416`; `backend/app/services/upload_jobs.py:1632`.

The internal facade replay is `duplicate_presentation_packaging` and safe to stop building in the normal path. The final upload replay is `qualified_supporting_evidence` and must remain because Investigation/Evidence, traceability, history, Diagnostics, current-session finding fallbacks and tests consume it.

### Operator explanation

The facade explanation is not evidence-qualified. It consumes heuristic archetypes, causal graph, static memory, counterfactuals and facility cognition. Its summary is prepended to otherwise legitimate `structural_explanation`, making the facade customer-visible even when the raw packages are not rendered.

Sources: `backend/explanations/operator_explanation_engine.py:6-78`; `backend/app/services/sii_intelligence.py:255-259,311`.

Proposed Phase 2 handling: stop prepending the facade summary and retain the already-built attribution/relationship explanation entries. Keep customer explanation centered on observed change, evidence strength, limitations, cause not established, and conservative engineering checks.

## Items proposed for removal from default customer authority

1. the eager `build_structural_cognition` invocation and `**structural_cognition` spread;
2. structural/static memory analog claims and active fingerprint packaging;
3. archetypes as customer findings;
4. `causality_graph` and causal/propagating explanation;
5. facade counterfactual scenarios, probability band and continuation claims;
6. facility-cognition, stability, recovery, compression and operational-time facade packages;
7. deterioration library/matches, domain pack, reference architecture, ontology/corpus/extensions;
8. facade benchmark/validation/institutional validation/audit/trust;
9. case studies, certification packs, SII/language standards and facade API-contract snapshot;
10. generated progression dataset and simulation;
11. synthetic multi-facility and multi-site packages;
12. fabricated operator-interaction model;
13. ephemeral persistent-cognition memory;
14. federation, graph exchange, distributed governance, cross-domain, training and fixed-query search packages;
15. synthesized facade replay construction (not the final upload replay);
16. behavioral/digital-twin packaging;
17. facade cognition confidence and facade evidence-lineage copy after qualified lineage parity is checked;
18. `operator_explanation_v2` and its prepended causal summary;
19. projected-time aliases from customer authority, subject to compatibility verification.

Research code need not be deleted. The proposed boundary is explicit, non-default internal/research/static access with no loosely trusted customer flag that re-enables it.

## Items proposed to remain

- formal finding IDs, classification, precedence, confidence contract and evidence facts;
- stable/no-material-change and explicit insufficient-evidence behavior;
- tenant/workspace/facility/system/asset identity and dataset/session scope;
- source rows/windows, timestamps, ingestion trust, provenance, traceability and decision integrity;
- data quality, sensor/integrity limitations and telemetry profile context;
- qualified baseline/current, relationship, persistence, operating-context, multiscale, temporal, covariance, expected-behavior and graph/structural evidence already present in SII/result projections;
- guarded primary driver/contributor language that explicitly preserves uncertainty and does not establish cause;
- qualified status/result fields and per-room records;
- concise engineering checks and the read-only/non-control boundary;
- final upload replay/timeline and its traceability use;
- genuine persisted behavioral-memory/Phase 4 architecture;
- Health Relevance and telemetry ingestion unchanged;
- independent research/static code and explicitly separate distributed/reference routes, subject to documentation and access-boundary review.

## `review_required` items

1. `structural_explanation`: mixed field. Approve removing only the facade summary while retaining evidence-based entries.
2. `review_window` / `review_window_hours` / `intervention_window`: useful neutral scheduling may remain, but it is heuristic and must be explicitly non-predictive.
3. `counterfactual_driver_ranking`: ambiguous name around a package that can contain ordinary supported-driver evidence; separate supported attribution before removal.
4. facade `evidence_lineage`: mixes real evidence references with heuristic graph/memory. Remove only after parity confirms qualified production traceability and bounded evidence remain.
5. `/api/facility/cognition-state` and audit-reference behavior: legacy customer-reachable projections directly consume facade fields; approve either internal/experimental classification or a narrow qualified response, without creating new architecture.
6. separate mounted distributed/ecosystem/reference APIs: they are not part of default upload but may be customer reachable. Phase 2 should not broadly redesign them unless approval explicitly includes authority gating.

## Dependency summary

### Frontend

- Direct facade dependencies are narrow: `distributed_cognition_governance` fallbacks and replay-frame visual components.
- Product Results/Review/Investigation/Evidence principally use `analysis_result`, qualified result fields and canonical/bounded SII evidence rather than facade causal/counterfactual/twin packages.
- Diagnostics consumes neutral review-window fields and a projected-time fallback.
- Raw technical metadata views expose whatever remains in the result.
- The final upload replay is a broad frontend dependency and must remain.

### Backend

- upload persistence/transport stores the whole `sii_intelligence` facade;
- facility cognition-state and audit reference routes directly project facade claims;
- system interpretation reads facade structural memory;
- evidence record/traceability consumes the final upload replay, not the facade replay after overwrite;
- runtime/audit/contracts/research packages consume facade fields internally;
- structural-cognition code has no formal-classification caller.

### Compatibility

- `projected_time_to_failure*` aliases are the only clearly named legacy field compatibility seam found in the default upload output.
- `REQUIRED_INTELLIGENCE_FIELDS` contains only legitimate core fields plus `structural_explanation`; it does not require facade packages.
- `build_sample_intelligence` also invokes/spreads the facade and powers reference/audit paths; it should not continue presenting research packages as default authority.
- final replay field shape is a de facto product compatibility contract and must remain.

## Tests requiring approved expectation changes

Customer-payload assertions in these suites should change after approval:

- `tests/test_structural_cognition.py`
- `tests/test_sii_reference_category.py`
- `tests/test_operational_legitimization.py`
- facade-coherence portions of `tests/test_cognition_coherence.py`
- projected-time/structural-memory expectations in `tests/test_data_upload.py`

Independent component tests such as `tests/test_structural_framework.py` should remain where research/static code remains. Replay, SII, finding, confidence, stable, insufficient, explanation, evidence transport and authorization tests become regression gates, not expectations to rewrite indiscriminately.

## P0.1 overlap assessment

No P0.1 overlap is required for the proposed Phase 2.

P0.1 owns canonical connector-result persistence/retrieval and the separate worktree/branch rooted at PR #107. This campaign can operate only on historical-upload authority and existing upload-result projection:

- `backend/app/services/sii_intelligence.py`
- `backend/app/services/structural_cognition.py` only if an explicit internal boundary/helper is needed
- `backend/app/services/upload_pipeline.py` only for preservation/assertion of final replay, not persistence architecture
- focused upload/facade tests

It must not modify `telemetry_analysis_window.py`, `telemetry_analysis_service.py`, `telemetry_lineage.py`, `telemetry_repository.py`, connector migrations, canonical result storage, or connector result retrieval. If implementation reveals a need to change those files/contracts, stop and report the exact overlap.

## Proposed Phase 2 file changes

Subject to checkpoint approval:

1. `backend/app/services/sii_intelligence.py`
   - stop eagerly calling/spreading the facade in default upload and sample customer authority;
   - retain the explicit qualified result/evidence fields;
   - stop prepending facade operator narrative;
   - separate/deprecate projected-time aliases without changing review arithmetic or thresholds.
2. `backend/app/services/structural_cognition.py` and/or a minimal adjacent boundary module
   - keep the research builder callable only through an explicit internal/experimental boundary;
   - do not add a client-controlled default query flag;
   - avoid changing any component algorithm.
3. `backend/app/services/system_interpretation.py`, `backend/api/cognition_contracts.py`, `backend/app/routers/facility.py`, and `backend/app/routers/audit.py` only as approved
   - remove facade authority dependencies or mark legacy/internal behavior;
   - preserve qualified relationship/path, traceability and limitations.
4. focused backend tests
   - replace “facade embedded by upload” assertions with “facade absent from customer upload” assertions;
   - keep independent research component tests;
   - add binding before/after finding/status/evidence comparisons and unsupported-language assertions.

Broad frontend and documentation edits remain deferred until Checkpoint 2.

## Expected customer-visible differences

- upload JSON no longer contains the facade packages listed above;
- no facade causal, counterfactual, probability, fleet, persistent cognition, twin, simulation, federation, training, certification or static-reference claims;
- `structural_explanation` begins with qualified observation/relationship explanation rather than “pressure is propagating” narrative;
- neutral review-window wording may remain if approved, while projected-time/failure aliases cease to be customer-authoritative;
- Results and formal finding classification should be unchanged;
- Investigation/Evidence retain relationship facts, qualified structural/graph evidence, source lineage, limitations and final upload replay;
- legacy cognition/reference endpoints may have a reduced qualified response or be explicitly internal, depending on approval.

## Expected payload impact

The completed current audit measured approximately **0.645 MB** saved when omitting the facade at its audit boundary and approximately **0.0024 seconds** of wall-time reduction. That is modest relative to the approximately **161 MB** 50-signal result. The expected default serialized payload is smaller, but P0.6 should not be represented as a material solution to overall payload scale.

Primary value: correctness, trust and authority clarity. Phase 2 should capture fixture-specific before/after total bytes, facade bytes, evidence bytes, serialization time, upload-intelligence build time and relevant wall time using identical inputs.

## Risks and gates

- Broad key deletion could remove the final upload replay because it shares the facade key name; preservation is mandatory.
- Broad deletion of `structural_explanation` would remove legitimate qualified explanation; only the facade summary should go.
- Facade lineage removal without parity could reduce audit trace detail; qualified traceability/evidence must be compared first.
- Legacy facility cognition/audit endpoints can re-expose facade claims even after the upload payload is cleaned.
- Projected-time aliases may have an undocumented internal client; verify before retaining or removing compatibility fields.
- Sample intelligence currently exposes the same facade without telemetry and can keep capability signaling alive if not addressed.
- Existing tests encode package presence as legitimacy; expectations must change only where authority is intentionally removed.
- Formal finding IDs/classification/confidence/persistence/limitations, stable status and insufficient-evidence status are binding blockers on any unexpected difference.
- No SII math, thresholds, persistence thresholds, Health Relevance, telemetry ingestion, behavioral memory, P0.1 or other roadmap work is authorized.

## Phase 1 disposition

The audit supports the existing P0.6 conclusion: the structural-cognition facade is a safe default-path removal candidate because it is post-classification packaging, while its capability-signaling content is not governed by the formal evidence-qualified finding authority. Approval should be conditioned on the preservation list and `review_required` decisions above.
