# Research: Internal Outcome-Grounded Health Relevance Audit

> Question: Is an internal, system-specific Health Relevance capability meaningfully distinct from Neraium's existing System Relevance and behavioral-memory behavior, and what outcome-grounded data and boundaries would it require?
> Date: 2026-08-26
> Status: Checkpoint 1 audit only
> Confidence: high for repository behavior; medium for future operational outcome sources that are not represented in this repository

## Executive conclusion

Health Relevance is meaningfully distinct and may proceed to design if Checkpoint 1 is approved.

The repository contains no class, table, service, API, or stored object literally named `SystemRelevance` or `system_relevance`. The concrete behavior serving the System Relevance role is relationship importance plus downstream relationship/finding ordering. It estimates which current telemetry relationship changes deserve attention from the magnitude and quality of the observed structural change. It does not learn which signals, relationships, assets, or subsystems repeatedly proved useful in independently validated real-world outcomes.

Behavioral memory is also distinct. It learns stable, mode-conditioned empirical signal and relationship structure from telemetry after data-quality and stability gates. It retains versions, snapshots, event references, association histories, and explicit non-causal limitations. It does not convert validated maintenance, inspection, fault, repair, no-fault, or false-positive outcomes into a health-usefulness representation.

The repository already has strong same-tenant finding, evidence, identity, and provenance building blocks. It does not yet have a normalized validated-outcome entity, a canonical outcome-to-evidence/structure linkage, or versioned Health Relevance state. Those additions are necessary; production SII, finding semantics, behavioral-memory learning, customer UI, and production ranking must remain untouched.

## Audit method and scope

This was a local repository audit. No external sources were needed because the question is about actual repository behavior. Searches covered relationship importance/relevance, SII, behavioral models and event memory, evidence packages and correlation, finding persistence and workflow, operator/engineer feedback, maintenance outcomes, known/explained states, facility/system/equipment/signal identity, historical outcome projections, authorization, provenance, and schema migrations.

Only this audit and the companion PRD were created. No migration, persistence, scoring, endpoint, UI, infrastructure, or production behavior was changed.

## 1. Exact existing System Relevance behavior

### 1.1 There is no separately named System Relevance subsystem

Repository-wide searches found `relationship_importance_score` and `relationship_importance_rationale`, but no `SystemRelevance`, `system_relevance`, health relevance, or relevance-state persistence. Therefore this audit uses **System Relevance** as the architectural name for the existing relationship-importance and attention-ordering behavior, not as a claim that a separately named subsystem exists.

### 1.2 Relationship importance is a deterministic telemetry score

For each eligible Pearson relationship edge, `score_relationship_importance` derives eight bounded factors:

- absolute correlation change magnitude;
- edge confidence;
- paired-sample persistence;
- inferred downstream/system scope;
- affected-metric severity heuristics;
- relationship-change novelty;
- data quality; and
- equipment/process involvement.

The fixed weighted sum is multiplied by a context factor. Context-only edges are multiplied by `0.35` and capped at `34`; context-driver edges use `0.82`; other edges use `1.0`. The function returns the score, a rationale, all ranking factors, column classifications, and relationship context. Source: `backend/app/services/relationship_baselines.py:276-367`.

The edge itself is a comparison between baseline and recent Pearson correlation. It preserves strengths, direction, confidence, sample counts, source row/time anchors, and the change type. Promotion to a finding candidate requires change-specific strength gates, correlation delta of at least `0.25`, and operator-primary eligibility. Promoted candidates and graph edges are ordered by relationship importance, then correlation delta and baseline coupling. Only the top five relationship changes are returned as `top_relationship_changes`. Source: `backend/app/services/relationship_baselines.py:620-730` and `docs/sii_math_specification.md:208-245`.

The score then affects attention order:

- analysis explanations sort relationship changes and grouped findings by it (`backend/app/services/analysis_explanations.py:180-192`, `backend/app/services/analysis_explanations.py:2552-2584`);
- live analysis reuses the same scorer and exposes it internally as a detection `severity_score` (`backend/app/services/live_intelligence.py:245-325`); and
- Evidence Package v1 preserves, but does not recalculate, the importance score and rationale (`backend/app/services/evidence_package.py:946-952`).

It is explicitly an evidence-ranking value, not physical criticality (`docs/sii_math_specification.md:208-245`). It uses no outcome, finding-review, work-order, maintenance-result, inspection-result, actor, provenance, or recovery input.

### 1.3 What existing System Relevance does

- Ranks current relationship-change evidence within an analysis.
- Down-ranks context-only and context-involved relationships.
- Preserves a transparent factor breakdown and rationale.
- Influences which relationships/findings appear first in explanation and live-detection results.
- Uses data sufficiency, persistence, signal class, novelty, and observed structural change.
- Remains deterministic and non-causal.

### 1.4 What existing System Relevance does not do

- It does not learn from validated real-world outcomes.
- It does not accumulate positive and negative outcome evidence across finding histories.
- It does not distinguish an independently documented outcome from feedback entered after Neraium review.
- It does not condition learned usefulness on outcome type, intervention/recovery windows, facility asset, or a complete operating-context stratum.
- It does not maintain outcome support counts, outcome diversity, contradictory evidence, uncertainty, or relevance versions.
- It does not estimate whether a frequent signal or relationship is useful for understanding health.
- It does not protect against survivorship bias through stable/no-fault exposure denominators.

## 2. Behavioral memory and why it is not Health Relevance

### 2.1 Identity and learning gate

Phase 4 resolves an infrastructure identity from organization, facility, system, subsystem/equipment group, schema fingerprint, or configured model ID. Memory writes fail closed when stable identity is absent or conflicting (`backend/app/engine/sii/behavioral_model.py:24-118`). The Phase 4 orchestrator loads a model only after identity is adequate and blocks learning for storage failure, identity conflict, schema change, poor data, unhealthy sensors, ambiguous mode, active observations, instability, or insufficient history (`backend/app/engine/sii/phase4.py:60-99`, `backend/app/engine/sii/phase4.py:170-200`; `backend/app/engine/sii/baseline_evolution.py:34-213`).

### 2.2 Signal and relationship memory

Accepted telemetry runs update robust signal centers/scales, observation counts, modes, drift/velocity/acceleration histories, residual history, sensor/data-quality history, and non-probability confidence. Relationship memory is keyed by relationship and operating mode and stores sample support, strength/covariance/mutual-information/lag history, volatility, persistence, lifecycle status, confidence, and association-only directionality. Relationships become inactive or retired after configured missed observations. Source: `backend/app/engine/sii/behavioral_model.py:602-776` and `backend/app/engine/sii/behavioral_model.py:779-902`.

The runtime store keeps append-only model versions, immutable snapshots, events, learning decisions, and baseline candidates/activations (`backend/app/engine/sii/behavioral_model_store.py:14-267`). Phase 4 states that its effect is persistent behavioral memory and evidence only (`backend/app/engine/sii_engine.py:963-986`).

### 2.3 Event memory does not perform outcome-grounded relevance learning

Event memory accepts typed external events including maintenance, equipment/sensor replacement, behavioral recovery, and human validation. It also records telemetry-derived residual, relationship lifecycle, operating-mode, and baseline-update events. External and telemetry-derived origins remain distinguishable (`backend/app/engine/sii/event_memory.py:8-45`, `backend/app/engine/sii/event_memory.py:47-140`, `backend/app/engine/sii/event_memory.py:155-189`).

Those event IDs are attached as model references, but `_update_relationship_memory` has no event or outcome parameter and cannot update usefulness from them. Current behavioral learning asks, "what structure repeatedly characterizes accepted operation?" Health Relevance would ask, "which preserved structural elements repeatedly co-occur with separately validated health outcomes, and under what context and uncertainty?"

### 2.4 Deferred Bayesian interface is not an implemented method

The existing Bayesian evidence module is deliberately inactive. It returns no posterior and requires validated likelihoods, calibration references, reliability analysis, versioned parameters, and acceptance approval before an updater could run (`backend/app/engine/sii/bayesian_evidence.py:8-95`). It is a useful safeguard pattern, not an existing Health Relevance implementation.

### 2.5 Legacy adaptive learning must not be used

`backend/app/services/adaptive_learning.py` contains dormant site-level feedback counts and a bounded sensitivity adjustment. Current product tests explicitly assert that uploads and operator feedback do not populate an adaptive-learning snapshot (`tests/test_adaptive_learning.py:27-68`). It is not wired into current production behavior.

It is unsuitable as Health Relevance because it:

- aggregates feedback at a derived `site_key`, including a `site::default` fallback;
- stores in globally keyed `latest_payloads` entries rather than an explicit tenant/facility/system outcome schema;
- reduces feedback to counts and a bounded sensitivity adjustment without exact finding/evidence/relationship contributions;
- lacks outcome validation status, independent-source provenance, context conditioning, contradictory evidence, and versioned relevance; and
- would overlap production sensitivity semantics forbidden in this task.

It must remain disabled and untouched.

## 3. Existing outcome-supporting data

### 3.1 Finding persistence and canonical identity

`finding_cases` provides a durable canonical finding ID, source kind (`evidence_run` or `live_finding`), source ID/key, immutable source snapshot, dataset scope, and `scope_storage_id`. Evidence findings retain source run, evidence/input/result hashes, provenance, and the exact finding snapshot (`backend/app/services/finding_workflow.py:59-150`, `backend/app/services/finding_workflow.py:179-226`). Live findings retain system ID, relationship identity, classification, baseline reference, timestamps, and latest evidence (`backend/app/services/finding_workflow.py:229-280`).

`finding_workflow_events` is append-only and versioned. Writes enforce scope before version/idempotency checks, preserve actor and timestamp, and are protected by no-update/no-delete triggers (`backend/app/services/runtime_db.py:141-169`, `backend/app/services/runtime_db.py:692-850`; `backend/app/services/finding_workflow.py:779-840`).

### 3.2 Operator/engineer feedback and maintenance workflow

The workflow supports assignments, work-order/external references, field reports, feedback, and resolution:

- feedback categories include confirmed issue, useful warning, expected behavior, false positive, nothing meaningful, known operational change, sensor/data problem, environmental cause, maintenance event, and ignore;
- feedback can retain note, arbitrary outcome text, action taken, intervention time, follow-up time, actor, and recorded time;
- field reports retain inspected/found/action text plus `problem_found` = yes/no/uncertain and investigation/escalation flags; and
- resolution uses a closed enum: issue found, no issue found, operational change, sensor issue, or maintenance performed.

Sources: `backend/app/models/api_models.py:347-425`, `backend/app/services/finding_workflow.py:869-923`, and `backend/app/routers/findings.py:201-315`.

This can supply candidate outcome evidence, but it is not automatically validated outcome truth. In particular, the evidence feedback route derives a validation outcome from category when none is supplied (`backend/app/services/evidence_store.py:144-177`), and UI copy currently calls an outcome "verified" merely because a signed-in engineer submitted it (`frontend/src/components/engineering/InvestigationOutcome.jsx:18-55`). Health Relevance must require an explicit validation decision and provenance rather than accepting those labels at face value.

### 3.3 Historical finding-outcome projections

Evidence hydration projects operator feedback categories into `confirmed`, `dismissed`, or `explained` validation statuses and can synthesize missing outcome text from the category. It also compares a current evidence record with the latest prior reviewed record sharing observation type and variables, labeling the drift-strength delta `improved`, `worsened`, or `unchanged`. A separate historical fact reports the dominant feedback category among similar prior observations (`backend/app/services/evidence_store.py:770-917`). Tests confirm these projections flow through evidence APIs/exports (`tests/test_data_upload.py:1029-1198`).

These are useful historical discovery aids, not validated outcome labels or causal intervention results: similarity is based on observation type/overlapping variables, validation status is category-derived, and the before/after direction is a telemetry drift delta. Health Relevance may reuse the underlying run IDs, timestamps, variables, feedback events, and evidence hashes, but it must not ingest the projected `validation_status`, `historical_fact`, or `before_after_intervention.direction` as validated truth without an explicit outcome and link review.

### 3.4 Known/explained and negative states

Analytical `known_operational_change` means directly observed operating context coincided with the relationship shift; the classification explicitly denies causal or exclusive attribution (`backend/app/services/finding_classification.py:142-156`). `unexplained_systemic_change` similarly does not diagnose cause or predict failure (`backend/app/services/finding_classification.py:174-194`).

Frontend review projections map known operational, sensor/data, environmental, expected behavior, and maintenance categories to "explained"; false positive, nothing meaningful, and ignore to "not useful" (`frontend/src/viewModels/findingReviewState.js:1-18`, `frontend/src/viewModels/findingReviewState.js:105-112`). These are useful negative/limiting outcome candidates only after validation quality and provenance are made explicit.

### 3.5 Evidence packages and lineage

Evidence records retain tenant/system/baseline/dataset identity, deterministic input/result/configuration hashes, engine/build versions, source-row anchors, evidence windows, timestamps, and a finding identity snapshot (`backend/app/services/analysis_provenance.py:87-115`; `backend/app/services/upload_evidence.py:245-386`; `backend/app/services/upload_evidence.py:389-534`).

Evidence Package v1 preserves the primary relationship, source edge ID, sample counts, persistence, existing relationship importance, operating context, supporting evidence, limitations, confidence dimensions, timeline, baseline reference, and provenance. Package construction fails closed when organization, analysis, baseline, dataset, relationship, timestamp, or exact baseline identity is missing/conflicting (`backend/app/services/evidence_package.py:822-972`).

Evidence-package correlation already enforces identical tenant, workspace, and system before associating two packages, and refuses optional facility/equipment conflicts (`backend/app/services/evidence_correlation.py:325-351`). It preserves shared signals/patterns, temporal/context relationship, evidence refs, content hashes, and rule provenance (`backend/app/services/evidence_correlation.py:353-474`). This is a strong pattern for future same-system linkage but is not itself an outcome model.

### 3.6 System, asset, and signal identity

Facility Context v1 stores site, systems, equipment, and signal mappings. Each mapping can bind raw tag to normalized name, system, equipment, subsystem, unit, sample rate, and alias (`backend/app/models/api_models.py:502-534`; `backend/app/services/facility_context.py:14-52`). The behavioral model has organization/facility/system/subsystem/equipment-group identity and a telemetry schema fingerprint (`backend/app/engine/sii/behavioral_model.py:24-118`). These can anchor Health Relevance, provided missing identities fail closed rather than falling back to broad site/default buckets.

## 4. Outcome data that is missing

The repository lacks:

1. A normalized, immutable **validated outcome** identity separate from a finding workflow label or note.
2. An explicit validation state and validation actor distinct from the person who entered the original report.
3. Source class and confirmation-bias provenance: independently documented, maintenance-system sourced, discovered after Neraium review, retrospective, or operator-confirmed.
4. Source reliability/confidence with a documented basis; existing arbitrary feedback text is not enough.
5. Typed occurrence and bounded pre/outcome/post-intervention/recovery windows.
6. A canonical many-to-many outcome-to-finding/evidence-package link with link provenance and confidence.
7. Exact outcome links to versioned signal, relationship, asset/equipment, and subsystem identities.
8. Negative exposure records for stable operation, unrelated maintenance, interventions with no behavioral response, and findings validated not useful.
9. Deduplication of one real-world incident represented by multiple findings, evidence packages, reviews, or workflow events.
10. A rule for superseded/corrected/retracted outcomes without deleting history.
11. An approved CMMS/inspection integration contract. No external maintenance or inspection source is present in the repository.
12. Outcome diversity, context coverage, recurrence, contradiction, and independence calculations.
13. Versioned Health Relevance state and per-outcome contribution provenance.

Free-text notes must remain supporting metadata. They must never be automatically converted to an outcome type or validation label.

## 5. Reuse and new-entity boundary

### Reuse without changing semantics

- `finding_cases` and append-only `finding_workflow_events` for canonical finding identity and candidate human evidence.
- `evidence_runs`, Evidence Package v1, and evidence-package correlation projections for exact evidence, relationship, time-window, context, hash, and lineage anchors.
- `DatasetScope.storage_id`, workspace membership resolution, and existing opaque-404 authorization patterns for tenant/workspace isolation.
- Facility Context v1 for facility/system/equipment/signal identity.
- Behavioral model relationship IDs, signal IDs, model versions, snapshots, and association-only limitations as read-only structural references.
- Existing audit-event conventions, idempotency, append-only triggers, and non-destructive migration tests.

### Do not reuse as the new model

- Relationship importance score: it answers attention relevance, not validated outcome relevance.
- Legacy adaptive-learning feedback counts or sensitivity adjustment.
- `latest_payloads` with an unscoped/default key.
- Evidence feedback category-to-outcome auto-mapping as proof of validation.
- Telemetry-derived event memory as validated outcome truth.
- Existing SII confidence values as Bayesian probabilities or outcome reliability.

### Minimal new entities likely necessary in Phase 3

Names remain proposals until Checkpoint 2 approves the final model.

1. `validated_outcomes`: immutable tenant/facility/system-scoped outcome fact, type, validation status, occurrence/window, source, actor/provenance, reliability, structured metadata, correction/retraction lineage.
2. `validated_outcome_links`: typed many-to-many links from an outcome to canonical finding IDs, evidence package/run IDs, behavioral model/version, signal/relationship/asset/subsystem IDs, temporal-window role, link confidence, and provenance.
3. `health_relevance_versions`: append-only versioned state for one scoped subject + context + experimental method, preserving component counts, uncertainty, state, configuration/threshold version, source watermark, and creation provenance.
4. `health_relevance_contributions`: inspectable signed/neutral contribution records linking each relevance version to the exact validated outcome link(s), including positive, negative, contradictory, excluded, or duplicate-suppressed treatment and reason.

A mutable current-state table is not necessary if the latest authorized version can be indexed deterministically. Phase 2 should prefer a latest-version query/index over duplicating state unless measured performance justifies a current pointer.

## 6. Proposed Health Relevance boundary

Health Relevance is internal, read-only intelligence about historical usefulness:

> Within one authorized tenant, facility, and system, and only within observed context, preserve how often a versioned signal, relationship, asset/equipment, or subsystem was linked to validated positive, negative, or contradictory real-world outcomes, with explicit uncertainty and provenance.

It must not:

- become a customer-facing score, ranking, diagnosis, or causal statement;
- alter SII weights, thresholds, classifications, finding generation, finding ordering, behavioral-memory updates, or customer UI;
- pool tenants, customers, facilities, systems, or unobserved contexts;
- treat telemetry frequency, a finding, an operator note, or a maintenance record alone as a validated outcome;
- infer cause from temporal sequence or recovery after intervention; or
- silently collapse components into one opaque scalar.

Potential future use in evidence ranking, investigation/compute prioritization, tie-breaking, or SII search-space selection is documentation only and requires a separate approved production task. Cross-system intelligence also requires a separate explicit architecture approval.

## 7. Proposed outcome model

Each outcome should preserve:

- immutable outcome ID and schema version;
- `scope_storage_id`, tenant, facility, system, and asset/equipment where applicable;
- typed outcome: confirmed maintenance event, inspection result, confirmed fault, confirmed degraded condition, repair, component replacement, operator-confirmed explanation, return toward expected behavior after intervention, expected/no-fault confirmation, or false-positive/not-useful review outcome;
- occurrence timestamp or bounded occurrence window;
- optional pre-outcome, outcome-period, post-intervention, and recovery windows, each explicitly typed;
- source type and source record ID;
- reporter actor, validator actor, validation time/status, reliability/confidence and basis;
- confirmation-bias provenance flags: independently documented, discovered after Neraium review, retrospective, maintenance-system sourced, operator-confirmed;
- structured metadata under an allowlisted/versioned schema; and
- correction, supersession, or retraction lineage without destructive overwrite.

An outcome becomes eligible for learning only after explicit validation. `pending`, `rejected`, `retracted`, ambiguous, unscoped, or free-text-only records remain inspectable but contribute nothing.

## 8. Proposed linkage model

The canonical path is:

```text
Validated Outcome
  -> validated outcome link(s)
  -> canonical finding case(s)
  -> evidence run / Evidence Package revision
  -> exact relationship(s), signal(s), asset/equipment, subsystem
  -> Behavioral Digital Model ID/version + operating context
```

Each hop must be explicit and integrity-checked. Temporal association is described as overlap, adjacency, pre-outcome, outcome-period, post-intervention, or recovery; never as cause. Links may be direct (maintenance record explicitly references a finding/work order) or reviewed associations, but link origin and confidence must remain visible. Derived links must not cross tenant/workspace/system and must not fill a missing system identity from similarity alone.

## 9. Proposed relevance representation

Relevance is a versioned evidence profile per:

```text
scope + system + subject_type + subject_id + context_fingerprint + method_version
```

Supported subject types are signal, relationship, asset/equipment, and subsystem. An evidence channel should be added only if Phase 2 demonstrates an independently useful, stable identity.

The representation should keep, at minimum:

- raw and deduplicated support count;
- distinct validated outcome count;
- recurrence across independent incidents/windows;
- outcome-type diversity;
- temporal consistency;
- context coverage and consistency;
- positive, negative, neutral, and contradictory evidence;
- independently documented versus Neraium-influenced evidence counts;
- uncertainty/credible or resampling interval appropriate to the method;
- evidence state: insufficient, emerging, supported, or contradictory;
- first/last evidence and last updated;
- method/configuration/threshold/schema version;
- complete included, excluded, and duplicate-suppressed provenance; and
- optional internal summary only if every component and contribution remains inspectable.

No global relevance is emitted when evidence exists only in a narrow context. Context-specific evidence remains context-specific.

## 10. Proposed minimum-evidence rules

Exact numeric thresholds are intentionally deferred to Checkpoint 2. Before any strong/supported state, the approved rules must require:

- more than one validated outcome; one event remains insufficient or at most emerging;
- recurrence across distinct deduplicated real-world incidents/windows, not repeated labels on one incident;
- explicit same-tenant, same-facility, same-system identity and exact subject linkage;
- complete provenance and an eligible validation status;
- positive and negative evidence handling, including stable/no-fault exposure where available;
- approved positive-to-negative balance and an explicit contradictory band;
- minimum context coverage for any claimed context, with no extrapolation outside it;
- approved outcome-type diversity or an explicit narrow-outcome limitation;
- separation or down-weighting of Neraium-influenced retrospective confirmation from independently documented outcomes; and
- deterministic state-machine thresholds, boundary tests, and configuration versioning.

Missing denominator, context, identity, or provenance evidence must lower/limit the state, never be interpreted as positive support.

## 11. Exactly two proposed experimental methods

### Method 1: Bayesian/shrinkage relevance updating

A transparent outcome-support model with approved priors and shrinkage toward insufficient evidence for sparse subjects/contexts. It should preserve positive and negative counts, posterior uncertainty, prior/configuration version, and per-outcome contributions. Existing heuristic confidence must not be converted into a probability or likelihood. Reliability strata/weights and prior parameters require Checkpoint 2 approval and deterministic sparse-data benchmarks.

Why appropriate: strong sparse-data behavior, interpretable uncertainty, incremental versioning, and natural resistance to a single event.

### Method 2: outcome-conditioned information measure

A regularized information-gain/mutual-information measure between a structural subject's observed state/presence and validated outcome class, computed only within the same approved context and with explicit negative/stable comparison windows. It must expose its contingency counts, smoothing/bias correction, effective sample size, uncertainty, and exclusions.

Why appropriate: it tests whether a subject adds outcome discrimination beyond raw frequency and can expose an irrelevant frequent signal, while remaining non-causal.

These are the only two methods proposed for implementation and comparison. Survival/time-to-event association, hierarchical cross-system models, standalone recurrence weighting, and precision/recall contribution may be documented as future research only; none may be implemented in this task.

## 12. Confirmation-bias risks and controls

| Risk | Existing evidence | Required control |
|---|---|---|
| Neraium-directed confirmation | Feedback is commonly recorded after a finding is reviewed. | Persist `discovered_after_neraium_review` and keep it separable from independent evidence. |
| UI overstates validation | Outcome form says "verified" based on signed-in submission. | Separate reporter from validator and require explicit validation status/basis. |
| Category auto-mapping | Missing feedback outcome can be derived from category. | Never treat derived outcome text as a validated-outcome label. |
| Selection/survivorship bias | Workflow data begins with Neraium findings. | Add stable/no-fault, unrelated-maintenance, no-response, and not-useful evidence. |
| Duplicate incident inflation | One incident may create multiple findings/packages/events. | Introduce incident/outcome deduplication keys and contribution suppression reasons. |
| Reviewer dependence | Same actor may report and validate. | Preserve actor roles and independent-validation flag; threshold policy must account for dependence. |
| Retrospective window fitting | Reviewers can select evidence after learning the outcome. | Preserve link author/time, window-selection method, and retrospective flag. |
| Positive-only asset history | Maintenance records tend to record interventions, not stable operation. | Require negative exposure/coverage or retain insufficient/emerging state. |

## 13. Tenant/facility/system isolation risks

Existing finding and evidence reads correctly filter by `scope_storage_id`, and workspace access resolves immutable dataset scope with opaque 404s for unauthorized facilities (`backend/app/services/workspace_authorization.py:83-124`; `backend/app/services/finding_workflow.py:302-321`; `tests/test_workspace_authorization.py:61-184`). Evidence correlation additionally requires same tenant/workspace/system.

Risks that Health Relevance must not inherit:

1. `latest_payloads` itself has only a global string key; isolation is safe only when every key embeds validated scope (`backend/app/services/runtime_db.py:191-195`, `backend/app/services/runtime_db.py:2052-2127`).
2. Runtime behavioral ledgers key by a model ID derived from configured infrastructure identity, not directly by `DatasetScope.storage_id` (`backend/app/engine/sii/behavioral_model_store.py:269-350`). If tenant/facility identity is absent or incorrectly supplied, collision or attachment risk exists. Health Relevance must store and query explicit scope columns and fail closed.
3. Legacy adaptive memory uses derived/default site keys and is unsuitable for multi-tenant learning.
4. Human-readable `system_id`, asset names, raw tags, or similarity must never be authorization boundaries.
5. Background workers must restore the exact immutable dataset scope from their queue/link record before any read or write.
6. Every foreign-key-like linkage must include or verify the same scope and system; an ID match alone is insufficient.

No cross-customer, fleet, or cross-system aggregation is authorized.

## 14. Production behavior that must remain untouched

- `score_relationship_importance`, its weights, context factors, sort order, and live `severity_score` use.
- SII formulas, weights, confidence, thresholds, classifications, finding semantics, and suppression behavior.
- Behavioral model learning gates, expected-behavior logic, baseline activation, relationship lifecycle, and event memory.
- Finding creation, persistence, classification, priority, and customer-facing workflow.
- Customer UI and API response semantics; no Health Relevance score/rank/diagnosis may appear.
- Evidence Package v1 meaning and evidence-correlation rules.
- AWS, IAM, DNS, infrastructure, deployment, production databases, and production configuration.

Phase 3, if approved, must be an isolated internal sidecar/read model whose outputs do not feed production decisions.

## 15. Expected later files/tables (not created in Phase 1)

Expected new backend modules, subject to Checkpoint 2:

- `backend/app/services/validated_outcomes.py`
- `backend/app/services/health_relevance.py`
- `backend/app/services/health_relevance_methods.py` or two explicitly named method modules
- `backend/app/services/health_relevance_benchmark.py`
- a strictly internal, permission-gated router only if inspection cannot be served by an existing internal tool
- non-destructive additions in `backend/app/services/runtime_db.py` or the repository's approved migration boundary
- focused tests under `tests/` for schema, authorization/isolation, linkage, provenance, state thresholds, method behavior, and benchmark cases

Expected proposed tables:

- `validated_outcomes`
- `validated_outcome_links`
- `health_relevance_versions`
- `health_relevance_contributions`

No frontend file is expected to change. No existing production scoring/classification service should change except possibly to expose read-only identifiers needed by the isolated linkage, and only after Checkpoint 2 approves that boundary.

## 16. Unresolved questions for Checkpoint 2

1. Who may validate each outcome type, and must reporter and validator differ for any type?
2. Which source systems, if any, are authoritative for maintenance/inspection outcomes?
3. What is the correction/retraction workflow and retention requirement?
4. What constitutes one deduplicated real-world incident across findings, work orders, and evidence packages?
5. Are facility and asset identities sufficiently stable today, or must outcome ingestion fail until mappings are approved?
6. Which negative/stable exposure source can provide a defensible denominator?
7. Which context dimensions are mandatory versus optional for each system type?
8. How should reliability strata affect eligibility or contribution without pretending heuristic confidence is probability?
9. What minimum validated outcomes, recurrence, balance, context coverage, and outcome diversity thresholds should define each state?
10. Is an internal endpoint necessary, or is a CLI/offline inspection tool safer for the experiment?
11. What retention and deletion rules apply to human-entered outcome metadata?
12. Should a relevance subject bind to raw signal identity, canonical signal mapping version, behavioral model version, or all three?

## Summary

Existing System Relevance ranks current telemetry relationship changes; behavioral memory learns stable empirical structure. Neither learns outcome-grounded usefulness. The finding/evidence stack supplies most lineage and isolation primitives, but candidate feedback is not equivalent to a validated outcome. A separate internal, same-system, context-conditioned, append-only sidecar with four minimal entities and exactly two experimental methods is justified, provided the tenant key is explicit and production behavior remains completely disconnected.
